from __future__ import annotations

import collections
import itertools
import json
import sys
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

T = TypeVar("T")

GLOBAL_DELAY = 0.005
MAX_SIZE: int = 2**28
PING_TIMEOUT: int = 900  # 15 minutes

TargetType = Union[cdp.target.TargetInfo, cdp.target.TargetID]


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

    def open(self, **kw):
        """
        opens the websocket connection. should not be called manually by users
        :param kw:
        :return:
        """
        # if not self.websocket or self.websocket.closed:
        if not self.websocket :
            try:
                self.reconnect_websocket()
                self.listener = Listener(self, self.reconnect_websocket)
                self.wait_for_socket_connection()
            except (Exception,) as e:
                if self.listener:
                    self.listener.cancel_event.set()
                raise
        if not self.listener or not self.listener.running:
            self.reconnect_websocket()
            self.listener = Listener(self, self.reconnect_websocket)
            self.listener.connected_event.wait(timeout=30)

        # when a websocket connection is closed (either by error or on purpose)
        # and reconnected, the registered event listeners (if any), should be
        # registered again, so the browser sends those events

        self._register_handlers()

    def wait_for_socket_connection(self):
        self.listener.connected_event.wait(timeout=30)

    def reconnect_websocket(self):
        self.close_socket_if_possible()
        self.websocket = websocket.WebSocketApp(self.websocket_url)

    def close(self):
        """
        closes the websocket connection. should not be called manually by users.
        """
        self.close_connections()

    def close_connections(self):
        if self.listener:
                self.listener.cancel_event.set()
                self.enabled_domains.clear()
                self.listener = None
            
        self.close_socket_if_possible()

    def close_socket_if_possible(self):
        if self.websocket:
            self.websocket.close()
            self.websocket = None
        

    def sleep(self, t: Union[int, float] = 0.25):
        self.update_target()
        time.sleep(t)

    def wait_to_be_idle(self, t: Union[int, float] = None):
        """
        waits until the event listener
        reports idle (which is when no new events had been received in .5 seconds
        or, 1 second when in interactive mode)

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
        if t is not None:
            self.sleep(t)

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
        self, cdp_obj: Generator[dict[str, Any], dict[str, Any], Any], _is_update=False
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
        if not self.listener or not self.listener.running:
            self.listener = Listener(self, self.reconnect_websocket)
        
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

                    self.send(domain_mod.enable(), _is_update=True)

                except:  # noqa - as broad as possible, we don't want an error before the "actual" request is sent
                    try:
                        self.enabled_domains.remove(domain_mod)
                    except:  # noqa
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

        is_interactive = getattr(sys, "ps1", sys.flags.interactive)
        self.cancel_event = threading.Event()  # Event for cancellation
        self.connected_event = threading.Event()  # Event for cancellation
        self._time_before_considered_idle = 0.10 if not is_interactive else 0.75
        self.idle = threading.Event()
        self.run()

    def run(self):
        self.task = threading.Thread(target=self.listener_loop, daemon=True)
        self.task.start()

    @property
    def time_before_considered_idle(self):
        return self._time_before_considered_idle

    @time_before_considered_idle.setter
    def time_before_considered_idle(self, seconds: Union[int, float]):
        self._time_before_considered_idle = seconds


    @property
    def running(self):
        if not self.task:
            return False
        if not self.task.is_alive():
            return False
        return True

    def listener_loop(self):
        while not self.cancel_event.is_set():
            while not self.connection.websocket:
                self.reconnect_ws()

            ws = self.connection.websocket
            def on_message(ws, message):
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
                
            def on_error(ws, error):
                # print(f"Error: {error}")
                pass

            def on_close(ws, x, w):
                # print("Connection closed")
                pass
            def on_open(ws):
                self.connected_event.set()

            ws.on_message = on_message
            ws.on_error = on_error
            ws.on_close = on_close
            ws.on_open = on_open

            ws.run_forever()
            
    def __repr__(self):
        s_idle = "[idle]" if self.idle.is_set() else "[busy]"
        s_running = f"[running: {self.running}]"
        s = f"{self.__class__.__name__} {s_running} {s_idle} >"
        return s