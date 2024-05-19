from __future__ import annotations

import asyncio
import atexit
import json
import urllib.parse
import urllib.request
import os
from typing import List, Union, Tuple

from .profiles import delete_profile, get_target_folders, run_check_and_delete_in_thread
from ..exceptions import DriverException
from .. import cdp
from . import util
from . import tab
from ._contradict import ContraDict
from .config import PathLike, Config, free_port, is_posix
from .connection import Connection
from .custom_storage_cdp import  get_cookies, set_cookies

import os
import signal

def kill_process(pid):
    os.kill(pid, signal.SIGTERM)

def get_folder_name_from_path(absolute_path):
    """
    Returns the folder name from an absolute path.

    Args:
        absolute_path (str): The absolute path to a directory or file.

    Returns:
        str: The folder name extracted from the absolute path.
    """
    return os.path.basename(absolute_path)

class Browser:
    _process: asyncio.subprocess.Process
    _process_pid: int
    _http: HTTPApi = None
    _cookies: CookieJar = None

    config: Config
    connection: Connection

    @classmethod
    async def create(
        cls,
        config: Config = None,
        *,
        profile_directory: PathLike = None,
        headless: bool = False,
        browser_executable_path: PathLike = None,
        browser_args: List[str] = None,
        sandbox: bool = True,
        **kwargs,
    ) -> Browser:
        """
        entry point for creating an instance
        """
        if not config:
            config = Config(
                profile_directory=profile_directory,
                headless=headless,
                browser_executable_path=browser_executable_path,
                browser_args=browser_args or [],
                sandbox=sandbox,
                **kwargs,
            )
        instance = cls(config)
        await instance.start()
        return instance

    def __init__(self, config: Config, **kwargs):
        """
        constructor. to create a instance, use :py:meth:`Browser.create(...)`

        :param config:
        """

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError(
                "{0} objects of this class are created using await {0}.create()".format(
                    self.__class__.__name__
                )
            )
        # weakref.finalize(self, self._quit, self)
        self.config = config

        self.targets: List = []
        """current targets (all types"""
        self.info = None
        self._target = None
        self._process = None
        self._process_pid = None
        self._keep_profile_directory = None
        self._is_updating = asyncio.Event()
        self.connection: Connection = None

    @property
    def websocket_url(self):
        return self.info.webSocketDebuggerUrl

    @property
    def main_tab(self) -> tab.Tab:
        """returns the target which was launched with the browser"""
        return sorted(self.targets, key=lambda x: x.type_ == "page", reverse=True)[0]

    @property
    def tabs(self) -> List[tab.Tab]:
        """returns the current targets which are of type "page"
        :return:
        """
        tabs = filter(lambda item: item.type_ == "page", self.targets)
        return list(tabs)

    @property
    def cookies(self) -> CookieJar:
        if not self._cookies:
            self._cookies = CookieJar(self)
        return self._cookies

    @property
    def stopped(self):
        if self._process and self._process.returncode is None:
            return False
        return True
        # return (self._process and self._process.returncode) or False

    def _handle_target_update(
        self,
        event: Union[
            cdp.target.TargetInfoChanged,
            cdp.target.TargetDestroyed,
            cdp.target.TargetCreated,
            cdp.target.TargetCrashed,
        ],
    ):
        """this is an internal handler which updates the targets when chrome emits the corresponding event"""

        if isinstance(event, cdp.target.TargetInfoChanged):
            target_info = event.target_info

            current_tab = next(
                filter(
                    lambda item: item.target_id == target_info.target_id, self.targets
                )
            )
            current_target = current_tab.target


        elif isinstance(event, cdp.target.TargetCreated):
            target_info: cdp.target.TargetInfo = event.target_info
            from .tab import Tab

            new_target = Tab(
                (
                    f"ws://{self.config.host}:{self.config.port}"
                    f"/devtools/page"  # all types are 'page' internally in chrome apparently
                    f"/{target_info.target_id}"                ),
                target=target_info,
                browser=self,
            )
            self.targets.append(new_target)


        elif isinstance(event, cdp.target.TargetDestroyed):
            current_tab = next(
                filter(lambda item: item.target_id == event.target_id, self.targets)
            )
            
            self.targets.remove(current_tab)

    async def get(
        self, url="chrome://welcome", new_tab: bool = False, new_window: bool = False, referrer=None
    ) -> tab.Tab:
        """top level get. utilizes the first tab to retrieve given url.

        convenience function known from selenium.
        this function handles waits/sleeps and detects when DOM events fired, so it's the safest
        way of navigating.

        :param url: the url to navigate to
        :param new_tab: open new tab
        :param new_window:  open new window
        :return: Page
        """
        if new_tab or new_window:
            # creat new target using the browser session
            target_id = await self.connection.send(
                cdp.target.create_target(
                    url, new_window=new_window, enable_begin_frame_control=True
                )
            )
            # get the connection matching the new target_id from our inventory
            connection = next(
                filter(
                    lambda item: item.type_ == "page" and item.target_id == target_id,
                    self.targets,
                )
            )

        else:
            # first tab from browser.tabs
            connection = next(filter(lambda item: item.type_ == "page", self.targets))
            # use the tab to navigate to new url
            frame_id, loader_id, *_ = await connection.send(cdp.page.navigate(url, referrer=referrer))
            # update the frame_id on the tab
            connection.frame_id = frame_id

        await connection.sleep(0.25)
        return connection

    async def start(self=None) -> Browser:
        """launches the actual browser"""
        if not self:
            print("use ``await Browser.create()`` to create a new instance")
            return
        if self._process or self._process_pid:
            if self._process.returncode is not None:
                return await self.create(config=self.config)
            print("ignored! this call has no effect when already running.")
            return

        self.config.host = self.config.host or "127.0.0.1"
        self.config.port = self.config.port or free_port()
        exe = self.config.browser_executable_path
        params = self.config()
        self._process: asyncio.subprocess.Process = (
            await asyncio.create_subprocess_exec(
                # self.config.browser_executable_path,
                # *cmdparams,
                exe,
                *params,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                close_fds=is_posix,
            )
        )

        self._process_pid = self._process.pid

        self._http = HTTPApi((self.config.host, self.config.port))
        self.base_folder_name = get_folder_name_from_path(self.config.profile_directory)
        instances = util.get_registered_instances()
        instances.add(self)
        
        await asyncio.sleep(0.25)
        for _ in range(5):
            try:
                self.info = ContraDict(await self._http.get("version"), silent=True)
            except (Exception,):
                if _ == 4:
                    pass
                await asyncio.sleep(0.5)
            else:
                break

        if not self.info:
            raise DriverException(
                (
                    """
                ---------------------
                Failed to connect to browser
                ---------------------
                One of the causes could be when you are running as root.
                """
                )
            )

        self.connection = Connection(self.info.webSocketDebuggerUrl, _owner=self)

        if self.config.autodiscover_targets:

            # self.connection.add_handler(
            #     cdp.target.TargetInfoChanged, self._handle_target_update
            # )
            # self.connection.add_handler(
            #     cdp.target.TargetCreated, self._handle_target_update
            # )
            # self.connection.add_handler(
            #     cdp.target.TargetDestroyed, self._handle_target_update
            # )
            # self.connection.add_handler(
            #     cdp.target.TargetCreated, self._handle_target_update
            # )
            #
            self.connection.handlers[cdp.target.TargetInfoChanged] = [
                self._handle_target_update
            ]
            self.connection.handlers[cdp.target.TargetCreated] = [
                self._handle_target_update
            ]
            self.connection.handlers[cdp.target.TargetDestroyed] = [
                self._handle_target_update
            ]
            self.connection.handlers[cdp.target.TargetCrashed] = [
                self._handle_target_update
            ]
            await self.connection.send(cdp.target.set_discover_targets(discover=True))
        await self
        fls = get_target_folders(instances)
        
        if fls:
            run_check_and_delete_in_thread(fls)
        # self.connection.handlers[cdp.inspector.Detached] = [self.close]
        # return self

    async def _get_targets(self) -> List[cdp.target.TargetInfo]:
        info = await self.connection.send(cdp.target.get_targets(), _is_update=True)
        return info

    async def update_targets(self):
        targets: List[cdp.target.TargetInfo]
        targets = await self._get_targets()
        for t in targets:
            for existing_tab in self.targets:
                existing_target = existing_tab.target
                if existing_target.target_id == t.target_id:
                    existing_tab.target.__dict__.update(t.__dict__)
                    break
            else:

                self.targets.append(
                    Connection(
                        (
                            f"ws://{self.config.host}:{self.config.port}"
                            f"/devtools/page"  # all types are 'page' somehow
                            f"/{t.target_id}"
                                                                            ),
                        target=t,
                        _owner=self,
                    )
                )

        await asyncio.sleep(0)

    async def __aenter__(self):

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type and exc_val:
            raise exc_type(exc_val)

    def __iter__(self):
        self._i = self.tabs.index(self.main_tab)
        return self

    def __next__(self):
        try:
            return self.tabs[self._i]
        except IndexError:
            del self._i
            raise StopIteration
        except AttributeError:
            del self._i
            raise StopIteration
        finally:
            if hasattr(self, "_i"):
                if self._i != len(self.tabs):
                    self._i += 1
                else:
                    del self._i


    def close(self):
        # No need we are killing
        # try:
        #     # asyncio.get_running_loop().create_task(self.connection.send(cdp.browser.close()))
        #     asyncio.get_event_loop().create_task(self.connection.aclose())
        # except RuntimeError:
        #     if self.connection:
        #         try:
        #             # asyncio.run(self.connection.send(cdp.browser.close()))
        #             asyncio.run(self.connection.aclose())
        #         except Exception:
        #             pass
        # except Exception:   
        #     pass
        
        for _ in range(3):
            try:
                # print("killing browser")
                kill_process(self._process_pid)
                # print("killed browser")            
                break
            except (Exception,):
                try:
                    kill_process(self._process_pid)
                    break
                except (Exception,):
                    try:
                        if hasattr(self, "browser_process_pid"):
                            os.kill(self._process_pid, 15)
                            break
                    except (TypeError,):
                        pass
                    except (PermissionError,):
                        
                        pass
                    except (ProcessLookupError,):
                        pass
                    except (Exception,):
                        raise
            self._process = None
            self._process_pid = None

        
        if self.config.is_temporary_profile:
            delete_profile(self.config.profile_directory)
        self.config.close()
        
    def __await__(self):
        # return ( asyncio.sleep(0)).__await__()
        return self.update_targets().__await__()

    def __del__(self):
        pass


class CookieJar:
    def __init__(self, browser: Browser):
        self._browser = browser
        # self._connection = connection

    async def get_all(
        self, requests_cookie_format: bool = False
    ) -> List[Union[cdp.network.Cookie]]:
        """
        get all cookies

        :param requests_cookie_format: when True, returns python http.cookiejar.Cookie objects, compatible  with requests library and many others.
        :type requests_cookie_format: bool
        :return:
        :rtype:

        """
        connection = None
        for tab in self._browser.tabs:
            if tab.closed:
                continue
            connection = tab
            break
        else:
            connection = self._browser.connection
        cookies = await connection.send(get_cookies())
        if requests_cookie_format:
            import requests.cookies

            return [
                requests.cookies.create_cookie(
                    name=c.name,
                    value=c.value,
                    domain=c.domain,
                    path=c.path,
                    expires=c.expires,
                    secure=c.secure,
                )
                for c in cookies
            ]
        return cookies

    async def set_all(self, cookies: List[cdp.network.CookieParam]):
        """
        set cookies

        :param cookies: list of cookies
        :type cookies:
        :return:
        :rtype:
        """
        connection = None
        for tab in self._browser.tabs:
            if tab.closed:
                continue
            connection = tab
            break
        else:
            connection = self._browser.connection
        await connection.send(set_cookies(cookies))
    async def clear(self):
        """
        clear current cookies

        note: this includes all open tabs/windows for this browser

        :return:
        :rtype:
        """
        connection = None
        for tab in self._browser.tabs:
            if tab.closed:
                continue
            connection = tab
            break
        else:
            connection = self._browser.connection
        await connection.send(cdp.storage.clear_cookies())


class HTTPApi:
    def __init__(self, addr: Tuple[str, int]):
        self.host, self.port = addr
        self.api = "http://%s:%d" % (self.host, self.port)

    async def get(self, endpoint: str):
        return await self._request(endpoint)

    async def _request(self, endpoint, method: str = "get", data: dict = None):
        url = urllib.parse.urljoin(
            self.api, f"json/{endpoint}" if endpoint else "/json"
        )
        if data and method.lower() == "get":
            raise DriverException("get requests cannot contain data")
        if not url:
            url = self.api + endpoint
        request = urllib.request.Request(url)
        request.method = method
        request.data = None
        if data:
            request.data = json.dumps(data).encode("utf-8")

        response = await asyncio.get_running_loop().run_in_executor(
            None, urllib.request.urlopen, request
        )
        return json.loads(response.read())


atexit.register(util.deconstruct_browser)
