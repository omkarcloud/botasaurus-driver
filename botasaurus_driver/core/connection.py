from __future__ import annotations

import collections
import itertools
import json
import threading
import time
from typing import (
    Generator,
    Union,
    Any,
    TypeVar,
)

import websocket
from queue import Queue, Empty
from ..exceptions import ChromeException


from . import util
from .. import cdp
import os

T = TypeVar("T")

GLOBAL_DELAY = 0.005
MAX_SIZE: int = 2**28
PING_TIMEOUT: int = 900  # 15 minutes

TargetType = Union[cdp.target.TargetInfo, cdp.target.TargetID]


def log_event(*values: object,):
    DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    if DEBUG:
        print(*values)

class SettingClassVarNotAllowedException(PermissionError):
    pass

def make_request_body(id, cdp_obj):
        method, *params = next(cdp_obj).values()
        if params:
            params = params.pop()
        return json.dumps({"method": method, "params": params, "id": id})

def parse_response(response, cdp_obj):
        if "error" in response:
            # set exception and bail out
            raise ChromeException(response["error"])
        try:
            # try to parse the result according to the py cdp docs.
            return cdp_obj.send(response["result"])
        except StopIteration as e:
            # exception value holds the parsed response
            return e.value
        raise ChromeException("could not parse the cdp response:\n%s" % response)

def wait_till_response_arrives(q: Queue, response_id, timeout):
            start_time = time.time()

            while True:
                try:
                    message = q.get(timeout=timeout)
                    if message['id'] == response_id:
                        return message
                except Empty:
                    raise TimeoutError("Response not received")

                # If the timeout has been exceeded, raise an exception
                if time.time() - start_time > timeout:
                    raise TimeoutError("Response not received")

                # # Wait for a short period before checking again
                # time.sleep(0.1)

class Connection:
    attached: bool = None
    websocket: websocket.WebSocketApp
    _target: cdp.target.TargetInfo

    def __init__(
        self,
        websocket_url: str,
        target: cdp.target.TargetInfo = None,
        _owner=None,
        **kwargs,
    ):
        self._target = target
        self.__count__ = itertools.count(0)
        self._owner = _owner
        self.queue = Queue()
        self.websocket_url: str = websocket_url
        self.websocket = None
        self.handlers = collections.defaultdict(list)
        self.recv_task = None
        self.enabled_domains = []
        self._last_result = []
        self._is_target_destroyed = False
        self.listener: Listener = None

        self.__dict__.update(**kwargs)

    @property
    def target(self) -> cdp.target.TargetInfo:
        return self._target

    @target.setter
    def target(self, target: cdp.target.TargetInfo):
        if not isinstance(target, cdp.target.TargetInfo):
            raise TypeError(
                "target must be set to a '%s' but got '%s"
                % (cdp.target.TargetInfo.__name__, type(target).__name__)
            )
        self._target = target

    @property
    def closed(self):
        if not self.websocket:
            return True
        return False
    def add_handler(
        self,
        event_type_or_domain,
        handler,
    ):
        """
        add a handler for given event

        if event_type_or_domain is a module instead of a type, it will find all available events and add
        the handler.

        if you want to receive event updates (network traffic are also 'events') you can add handlers for those events.
        handlers can be regular callback functions or coroutine functions (and also just lamba's).
        for example, you want to check the network traffic:

        .. code-block::

            page.add_handler(cdp.network.RequestWillBeSent, lambda event: print('network event => %s' % event.request))

        the next time you make network traffic you will see your console print like crazy.

        :param event_type_or_domain:
        :type event_type_or_domain:
        :param handler:
        :type handler:

        :return:
        :rtype:
        """
        self.handlers[event_type_or_domain].append(handler)

    def open(self, **kw):
        """
        opens the websocket connection. should not be called manually by users
        :param kw:
        :return:
        """
        if self._is_target_destroyed:
            self.raise_connection_failure_exception()

        # if not self.websocket or self.websocket.closed:
        if not self.websocket :
            try:
                self._create_websocket()
                self.listener = Listener(self, self.create_websocket)
                self.wait_for_socket_connection()
            except (Exception,) as e:
                raise
        if not self.listener or not self.listener.running:
            self.create_websocket()
            self.listener = Listener(self, self.create_websocket)
            self.wait_for_socket_connection()

        # when a websocket connection is closed (either by error or on purpose)
        # and reconnected, the registered event listeners (if any), should be
        # registered again, so the browser sends those events

        self._register_handlers()

    def raise_connection_failure_exception(self):
        raise Exception(self._connection_failure_message)

    def wait_for_socket_connection(self):
        start_time = time.time()
        self._connection_failure_message = None
        result = self.listener.connected_event.wait(timeout=30)
        elapsed_time = time.time() - start_time
        if self._connection_failure_message:
            self.raise_connection_failure_exception()
        
        if not result:
            raise TimeoutError("Failed to establish a connection")
        log_event(f"Connected in {elapsed_time:.2f} seconds")

    def create_websocket(self):
        self.close_socket_if_possible()
        self._create_websocket()

    def _create_websocket(self):
        self.websocket = websocket.WebSocketApp(self.websocket_url)

    def close(self):
        """
        closes the websocket connection. should not be called manually by users.
        """
        self.close_connections()

    def close_connections(self, close_connections=True):
        if self.listener:
                self.enabled_domains.clear()
                self.listener = None
            
        self.close_socket_if_possible(close_connections)

    def close_socket_if_possible(self, close_connections=True):
        if self.websocket:
            if close_connections:
                self.websocket.close()
            self.websocket = None

    def sleep(self, t: Union[int, float] = 0.25):
        self.update_target()
        time.sleep(t)

    def wait(self, t: Union[int, float] = None):
        """
        waits until the event listener reports idle (no new events received in certain timespan).
        when `t` is provided, ensures waiting for `t` seconds, no matter what.

        :param t:
        :type t:
        :return:
        :rtype:
        """
        self.update_target()

        try:
            self.listener.idle.wait(timeout=t)
        except TimeoutError:
            if t is not None:
                # explicit time is given, which is now passed
                # so bail out early
                return
        except AttributeError:
            # no listener created yet
            pass

    # def __getattr__(self, item):
    #     """:meta private:"""
    #     try:
    #         return getattr(self.target, item)
    #     except AttributeError:
    #         raise

    def __enter__(self):
        """:meta private:"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """:meta private:"""
        self.close()
        if exc_type and exc_val:
            raise exc_type(exc_val)

    def update_target(self):
        target_info: cdp.target.TargetInfo = self.send(
            cdp.target.get_target_info(self.target.target_id), _is_update=True
        )
        self.target = target_info

    def send(
        self, cdp_obj: Generator[dict[str, Any], dict[str, Any], Any], _is_update=False, wait_for_response=True
    ) -> Any:
        """
        send a protocol command. the commands are made using any of the cdp.<domain>.<method>()'s
        and is used to send custom cdp commands as well.

        :param cdp_obj: the generator object created by a cdp method

        :param _is_update: internal flag
            prevents infinite loop by skipping the registeration of handlers
            when multiple calls to connection.send() are made
        :return:
        """
        self.open()
        if not self.websocket or self.closed:
            return
        
        return self.perform_send(cdp_obj, _is_update, wait_for_response)

    def perform_send(self, cdp_obj, _is_update=False, wait_for_response=True):
        if not self.listener or not self.listener.running:
            self.listener = Listener(self, self.create_websocket)
        
        tx_id = next(self.__count__)
        tx  = make_request_body(id=tx_id, cdp_obj = cdp_obj)
        if not _is_update:
            self._register_handlers()
        try:
          self.websocket.send(tx)

        # except (exceptions.ConnectionClosed,exceptions.ConnectionClosedError, ConnectionResetError):
        except Exception as e:
        #   print('faced websocket send exception', e)
          raise           
        
        if wait_for_response:
            MAX_WAIT = 200
            result = wait_till_response_arrives(self.queue, tx_id , MAX_WAIT)
            result = parse_response(result, cdp_obj)

            return result
    def _register_handlers(self):
        """
        ensure that for current (event) handlers, the corresponding
        domain is enabled in the protocol.

        """
        seen = []
        # save a copy of current enabled domains in a variable
        # domains will be removed from this variable
        # if it is still needed according to the set handlers
        # so at the end this variable will hold the domains that
        # are not represented by handlers, and can be removed
        enabled_domains = self.enabled_domains.copy()
        for event_type in self.handlers.copy():
            domain_mod = None
            if len(self.handlers[event_type]) == 0:
                self.handlers.pop(event_type)
                continue
            if isinstance(event_type, type):
                domain_mod = util.cdp_get_module(event_type.__module__)
            if domain_mod in self.enabled_domains:
                # at this point, the domain is being used by a handler
                # so remove that domain from temp variable 'enabled_domains' if present
                if domain_mod in enabled_domains:
                    enabled_domains.remove(domain_mod)
                continue
            elif domain_mod not in self.enabled_domains:
                if domain_mod in (cdp.target, cdp.storage):
                    # by default enabled
                    continue
                try:
                    # we add this before sending the request, because it will
                    # loop indefinite
                    self.enabled_domains.append(domain_mod)

                    self.send(domain_mod.enable(), _is_update=True, wait_for_response=False)

                except:  # noqa - as broad as possible, we don't want an error before the "actual" request is sent
                    try:
                        self.enabled_domains.remove(domain_mod)
                    except:  # noqa
                        continue
                finally:
                    continue
        for ed in enabled_domains:
            # we started with a copy of self.enabled_domains and removed a domain from this
            # temp variable when we registered it or saw handlers for it.
            # items still present at this point are unused and need removal
            self.enabled_domains.remove(ed)


class Listener:
    def __init__(self, connection: Connection, reconnect_ws):
        self.connection = connection
        self.reconnect_ws = reconnect_ws
        
        self.task: threading.Thread = None

        # when in interactive mode, the loop is paused after each return
        # and when the next call is made, it might still have to process some events
        # from the previous call as well.

        # while in "production" the loop keeps running constantly
        # (and so events are continuous processed)

        # therefore we should give it some breathing room in interactive mode
        # and we can tighten that room when in production.

        # /example/demo.py runs ~ 5 seconds faster, which is quite a lot.

        self.connected_event = threading.Event()  # Event for cancellation
        self.idle = threading.Event()
        self.run()

    def run(self):
        self.task = threading.Thread(target=self.listener_loop, daemon=True)
        self.task.start()



    @property
    def running(self):
        if not self.task:
            return False
        if not self.task.is_alive():
            return False
        return True
    def set_idle(self):
        self.idle.set()

    def clear_idle(self):
        self.idle.clear()

    def handle_message(self, message):
                message = json.loads(message)
                if "id" in message:
                    # pass
                    self.connection.queue.put(message)
                else:
                    try:
                        event = cdp.util.parse_json_event(message)
                    except KeyError as e:
                        return
                    except Exception as e:
                        return
                    try:
                        if type(event) in self.connection.handlers:
                            callbacks = self.connection.handlers[type(event)]
                        else:
                            return

                        if not len(callbacks):
                            return

                        for callback in callbacks:
                            try:
                                callback(event)
                            except Exception as e:
                                raise
                    except:
                        return
                    return

    def listener_loop(self):
            e = None
            while not self.connection.websocket:
                self.reconnect_ws()

            def on_message(ws, message):
                self.clear_idle()
                self.handle_message(message)
                self.set_idle()
                
            def on_error(ws, error):
                nonlocal e
                e = str(error)
                log_event('error ws', error, ws.url)
                self.set_idle()
                # print(f"Error: {error}")
                pass

            def on_close(ws, x, w):
                log_event('closed ws', ws.url)
                self.set_idle()
                # print("Connection closed")
                pass
            def on_open(ws):
                log_event('opened ws', ws.url)
                self.connected_event.set()
                self.set_idle()
            
            ws = self.connection.websocket
            ws.on_message = on_message
            ws.on_error = on_error
            ws.on_close = on_close
            ws.on_open = on_open
            log_event('running ws')

            ws.run_forever()
            
            if e:
                # is_target_destroyed
                # can be 'Connection to remote host was lost' in e
                if 'No such target id:' in e:
                    self.connection._is_target_destroyed = True
                    self.connection._connection_failure_message = 'The target tab or iframe is no longer available. This may have occurred because you navigated to a different page, reloaded the current page, or closed the tab.'
                else: 
                    self.connection._connection_failure_message = e
            
            # 'Connection refused' in e:
            # Already closed so no need to close again
            self.connection.close_connections(close_connections=False)

            # Hackish fix for wait_for_socket_connection
            self.connected_event.set()
            return
    def __repr__(self):
        s_idle = "[idle]" if self.idle.is_set() else "[busy]"
        s_running = f"[running: {self.running}]"
        s = f"{self.__class__.__name__} {s_running} {s_idle} >"
        return s