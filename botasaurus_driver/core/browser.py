from __future__ import annotations

import json
import subprocess
import atexit
import os
from typing import List, Union

import time
import urllib.request
from urllib.error import URLError, HTTPError
from .retry_on_error import retry_if_is_error
from .profiles import delete_profile, get_target_folders, run_check_and_delete_in_thread
from .. import cdp
from . import util
from . import tab
from .config import PathLike, Config, free_port, is_posix
from .connection import Connection
from .custom_storage_cdp import get_cookies, set_cookies
from .env import is_docker
from time import sleep
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


def ensure_chrome_is_alive(url):
    start_time = time.time()
    timeout = 5  # Adjust this value based on your requirements
    duration = 15  # Duration to keep trying
    retry_delay = 0.1
    while time.time() - start_time < duration:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    data = response.read().decode('utf-8')
                    return json.loads(data)
        except (URLError, HTTPError) as e:
            time.sleep(retry_delay)  # Wait before retrying
            continue

    raise Exception(f"Failed to connect to Chrome URL: {url}.")


def wait_for_graceful_close(_process):
    retries = 10
    delay = 0.05

    for _ in range(retries):
        if _process.poll() is not None:
            return True
        time.sleep(delay)

    return _process.poll() is not None


def terminate_process(process: subprocess.Popen):
    try:
        process.terminate()
        process.wait()
    except Exception:
        try:
            process.kill()
        except Exception:
            try:
                os.kill(process.pid, signal.SIGTERM)
            except TypeError:
                pass
            except PermissionError:
                pass
            except ProcessLookupError:
                pass
            except Exception:
                raise


class Browser:
    _process = None
    _process_pid: int
    _cookies: CookieJar = None

    config: Config
    connection: Connection

    @classmethod
    def create(
        cls,
        config: Config = None,
        *,
        profile_directory: PathLike = None,
        headless: bool = False,
        chrome_executable_path: PathLike = None,
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
                chrome_executable_path=chrome_executable_path,
                browser_args=browser_args or [],
                sandbox=sandbox,
                **kwargs,
            )
        instance = cls(config)
        instance.start()
        return instance

    def __init__(self, config: Config):
        """
        constructor. to create a instance, use :py:meth:`Browser.create(...)`

        :param config:
        """

        # weakref.finalize(self, self._quit, self)
        self.config = config

        self.targets: List = []
        """current targets (all types"""
        self.info = None
        self._target = None
        self._process = None
        self._process_pid = None
        self._keep_profile_directory = None
        self._is_updating = False
        self.connection: Connection = None

    @property
    def websocket_url(self):
        return self.info["webSocketDebuggerUrl"]

    @property
    def main_tab(self) -> tab.Tab:
        """returns the target which was launched with the browser"""
        return sorted(self.targets, key=lambda x: x._target.type_ == "page", reverse=True)[0]

    @property
    def tabs(self) -> List[tab.Tab]:
        """returns the current targets which are of type "page"
        :return:
        """
        tabs = filter(lambda item: item._target.type_ == "page", self.targets)
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


    def fix_browser(self, connection):
        if self.config.headless:
            response, error = connection.send(
                cdp.runtime.evaluate(
                expression="navigator.userAgent",
                user_gesture=True,
                await_promise=True,
                return_by_value=True,
                allow_unsafe_eval_blocked_by_csp=True,
            )
            )
            if response and response.value:
                ua = response.value
                connection.send(
                    cdp.network.set_user_agent_override(
                        user_agent=ua.replace("Headless", ""),
                    ), wait_for_response=False
                )
        if self.config.block_images_and_css:
            connection.block_images_and_css()
        if self.config.block_images:
            connection.block_images()

    def wait(self, time: Union[float, int] = 1) -> Browser:
        """wait for <time> seconds. important to use, especially in between page navigation

        :param time:
        :return:
        """
        return sleep(time)

    sleep = wait
    """alias for wait"""
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
                    lambda item: item.target.target_id == target_info.target_id, self.targets
                )
            )
            # todo: maybe connections need to be reinited?
            current_tab.target = target_info
        elif isinstance(event, cdp.target.TargetCreated):
            target_info: cdp.target.TargetInfo = event.target_info
            

            new_target = self.make_tab(target_info)
            
            page_type = target_info.type_
            if page_type in ["page"]:
                # only fix pages because other type's like iframe causes blocking of websockets
                self.fix_browser(new_target)

            self.targets.append(new_target)

        elif isinstance(event, cdp.target.TargetDestroyed):
            current_tab = next(
                filter(lambda item: item.target.target_id == event.target_id, self.targets)
            )
            current_tab.close_connections()
            self.targets.remove(current_tab)

    def make_tab(self, target_info):
        from .tab import Tab
        if target_info.type_ == 'iframe':
            page_type = 'page'
        else:
            page_type = target_info.type_ or 'page'

        return Tab(
                (
                    f"ws://{self.config.host}:{self.config.port}"
                    f"/devtools/{page_type}"  # all types are 'page' internally in chrome apparently
                    f"/{target_info.target_id}"
                ),
                target=target_info,
                browser=self)

    def get(
        self,
        url="chrome://welcome",
        new_tab: bool = False,
        new_window: bool = False,
        referrer=None,
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
            target_id = self.connection.send(
                cdp.target.create_target(
                    url, new_window=new_window, enable_begin_frame_control=True
                )
            )
            # get the connection matching the new target_id from our inventory
            connection:Connection = next(
                filter(
                    lambda item: item._target.type_ == "page" and item.target.target_id == target_id,
                    self.targets,
                )
            )
            connection.browser = self

        else:
            # first tab from browser.tabs
            connection = self.get_first_tab()
            # use the tab to navigate to new url
            # connection.send(cdp.runtime.disable())
            frame_id, _, *_ = connection.send(cdp.page.navigate(url, referrer=referrer))
            # update the frame_id on the tab
            connection.frame_id = frame_id
            connection.browser = self

        time.sleep(0.25)
        return connection

    def get_first_tab(self):
        return next(filter(lambda item: item._target.type_ == "page", self.targets))

    def start(self=None) -> Browser:

        self.config.host = self.config.host or "127.0.0.1"
        self.config.port = self.config.port or free_port()
        exe = self.config.chrome_executable_path
        params = self.config()

        self.create_chrome_with_retries(exe, params)

        self.connection = Connection(self.info["webSocketDebuggerUrl"], _owner=self)

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

        self._process_pid = self._process.pid
        self.base_folder_name = get_folder_name_from_path(self.config.profile_directory)

        # await self
        instances = util.get_registered_instances()
        instances.add(self)

        # CLEAN UO
        fls = get_target_folders(instances)

        if fls:
            run_check_and_delete_in_thread(fls)

        self.connection.send(cdp.target.set_discover_targets(discover=True), wait_for_response=False)
        # self.connection.wait_to_be_idle()
        self.update_targets()
    def create_chrome_with_retries(self, exe, params):
        @retry_if_is_error()
        def run():
            process = subprocess.Popen(
                [exe, *params],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=is_posix,
            )
            chrome_url = f"http://{self.config.host}:{self.config.port}/json/version"
            # time.sleep(0.5)
            try:
                self.info = ensure_chrome_is_alive(chrome_url)
                self._process = process
            except:
                terminate_process(process)
                raise

        run()

    def grant_all_permissions(self):
        """
        grant permissions for:
            accessibilityEvents
            audioCapture
            backgroundSync
            backgroundFetch
            clipboardReadWrite
            clipboardSanitizedWrite
            displayCapture
            durableStorage
            geolocation
            idleDetection
            localFonts
            midi
            midiSysex
            nfc
            notifications
            paymentHandler
            periodicBackgroundSync
            protectedMediaIdentifier
            sensors
            storageAccess
            topLevelStorageAccess
            videoCapture
            videoCapturePanTiltZoom
            wakeLockScreen
            wakeLockSystem
            windowManagement
        """
        permissions = list(cdp.browser.PermissionType)
        permissions.remove(cdp.browser.PermissionType.FLASH)
        permissions.remove(cdp.browser.PermissionType.ACCESSIBILITY_EVENTS)
        permissions.remove(cdp.browser.PermissionType.VIDEO_CAPTURE_PAN_TILT_ZOOM)
        
        permissions.remove(cdp.browser.PermissionType.CAPTURED_SURFACE_CONTROL)
        self.connection.send(cdp.browser.grant_permissions(permissions))

    def _get_targets(self) -> List[cdp.target.TargetInfo]:
        info = self.connection.send(cdp.target.get_targets(), _is_update=True)
        return info

    def update_targets(self):
        targets = self._get_targets()
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
        time.sleep(0)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, _):
        if exc_type and exc_val:
            raise exc_type(exc_val)

    def __iter__(self):
        self._i = self.tabs.index(self.main_tab)
        return self

    def __getitem__(self, item: Union[str, int]):
        """
        allows to get py:obj:`tab.Tab` instances by using browser[0], browser[1], etc.
        a string is also allowed. it will then return the first tab where the py:obj:`cdp.target.TargetInfo` object
        (as json string) contains the given key, or the first tab in case no matches are found. eg:
        `browser["google"]` gives the first tab which has "google" in it's serialized target object.

        :param item:
        :type item:
        :return:
        :rtype: tab.Tab
        """
        if isinstance(item, int):
            return self.tabs[item]
        if isinstance(item, str):
            for t in self.tabs:
                if item.lower() in str(t.target.to_json()).lower():
                    return t
            else:
                return self.tabs[0]

    def __reversed__(self):
        return reversed(list(self.tabs))

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
        # close gracefully
        self.close_tab_connections()
        self.close_chrome()
        self.close_browser_connection()
        if self._process:
            if not wait_for_graceful_close(self._process):
                terminate_process(self._process)
        self._process = None
        self._process_pid = None

        if self.config.is_temporary_profile:
            delete_profile(self.config.profile_directory)
        self.config.close()
        instances = util.get_registered_instances()
        try:
            instances.remove(self)
        except KeyError:
            pass

        if is_docker:
            util.close_zombie_processes()

    def close_browser_connection(self):
        try:
            if self.connection:
                self.connection.close()
                # Fixed a bug. here
                # self.connection = None
        except Exception as e:
            print(e)

    def close_tab_connections(self):
        try:
            while self.targets:
                # close just connections, chrome tabs are closed
                self.targets.pop().close_connections()
        except Exception as e:
            print(e)

    def close_chrome(self):
        try:
            if self.connection:
                self.connection.send(cdp.browser.close())
                self.connection = None
        except Exception as e:
            print(e)

    def __del__(self):
        pass

class CookieJar:
    def __init__(self, browser: Browser):
        self._browser = browser
        # self._connection = connection

    def get_all(
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
        cookies = connection.send(get_cookies())
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

    def set_all(self, cookies: List[cdp.network.CookieParam]):
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
        connection.send(set_cookies(cookies))

    def clear(self):
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
        connection.send(cdp.storage.clear_cookies())


atexit.register(util.deconstruct_browser)
