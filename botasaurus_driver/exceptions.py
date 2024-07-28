class DriverException(Exception):
    """Base webdriver exception."""

    def __init__(self, msg = None) -> None:
        super().__init__()
        self.msg = msg

    def __str__(self) -> str:
        exception_msg = f"{self.msg}"
        return exception_msg

class GoogleCookieConsentException(DriverException):
    """
    Thrown when unable to consent to Google cookies.
    """
    def __init__(self, message="Unable to consent to Google cookies."):
        self.message = message
        super().__init__(self.message)

class IframeNotFoundException(DriverException):
    def init(self, iframe_id):
        super().__init__(f"Iframe {iframe_id} does not exist in the targets.")


class NoProfileException(DriverException):
    def init(self):
        super().__init__(f"No profile provided.")

class InvalidProfileException(DriverException):
    def init(self):
        super().__init__(f"Invalid profile format. Profile must be a dictionary or None.")
class ElementWithTextNotFoundException(DriverException):
    def __init__(self, text):
        super().__init__(f"Cannot find element containing text: '{text}'.")

class ElementWithSelectorNotFoundException(DriverException):
    def __init__(self, selector):
        super().__init__(f"Cannot find element with selector: '{selector}'.")


class InputElementForLabelNotFoundException(DriverException):
    def __init__(self, label):
        super().__init__(f"Cannot find input element for label: '{label}'.")

class CheckboxElementForLabelNotFoundException(DriverException):
    def __init__(self, label):
        super().__init__(f"Cannot find checkbox element for label: '{label}'.")

class PageNotFoundException(DriverException):
    def __init__(self, target, wait=None):
        if not wait:
            super().__init__(f"Page '{target}' not found.")
        else:
            super().__init__(f"Page '{target}' not found within the specified wait time of {wait} seconds.")

class CloudflareDetectionException(DriverException):
    def __init__(self):
        super().__init__("Cloudflare has detected us.") 

class ElementInitializationException(DriverException):
    def __init__(self, message):
        super().__init__(message)  # Exception message for element initialization errors

 
class DetachedElementException(DriverException):
    def __init__(self):
        super().__init__("Element has been removed and currently not connected to DOM.")

class ElementPositionNotFoundException(DriverException):
    def __init__(self, element):
        super().__init__(f"Could not find position for {element}.")

class ElementPositionException(DriverException):
    def __init__(self):
        super().__init__("Could not determine position of element. Probably because it's not in view or hidden.")


class ElementScreenshotException(DriverException):
    def __init__(self):
        super().__init__(
                        "Could not take screenshot. The page may not have finished loading yet."
        )

class ScreenshotException(DriverException):
    def __init__(self):
        super().__init__(
                        "Could not take screenshot. The page may not have finished loading yet."
        )


class InvalidFilenameException(DriverException):
    def __init__(self, filename):
        super().__init__(f"Invalid filename: '{filename}'.")

class ChromeException(DriverException):
    def __init__(self, *args, **kwargs):  # real signature unknown

        self.message = None
        self.code = None
        self.args = args
        if isinstance(args[0], dict):

            self.message = args[0].get("message", None)  # noqa
            self.code = args[0].get("code", None)

        elif hasattr(args[0], "to_json"):

            def serialize(obj, _d=0):
                res = "\n"
                for k, v in obj.items():
                    space = "\t" * _d
                    if isinstance(v, dict):
                        res += f"{space}{k}: {serialize(v, _d + 1)}\n"
                    else:
                        res += f"{space}{k}: {v}\n"

                return res

            self.message = serialize(args[0].to_json())

        else:
            self.message = "| ".join(str(x) for x in args)

    def __str__(self):
        return f"{self.message} [code: {self.code}]" if self.code else f"{self.message}"


class JavascriptException(ChromeException):

    def __init__(self, *args, **kwargs):  # real signature unknown
        
        super().__init__(*args, **kwargs)


class SyntaxError(DriverException):
    def __init__(self, message):  # real signature unknown
        super().__init__(f"Syntax Error in the following code:\n\n{message}\nPlease review the syntax and run again.")

class ReferenceError(DriverException):
    def __init__(self, message):  # real signature unknown
        super().__init__(f"ReferenceError in the following code:\n\n{message}\nPlease review the code and run again.")


class JavascriptSyntaxException(JavascriptException):

    def __init__(self, msg = "Syntax error in the js code.") -> None:
        self.msg = msg

    def __str__(self) -> str:
        exception_msg = f"{self.msg}"
        return exception_msg

class JavascriptRuntimeException(JavascriptException):
    def __init__(self, msg = "Runtime error in the js code.") -> None:
        self.msg = msg

    def __str__(self) -> str:
        exception_msg = f"{self.msg}"
        return exception_msg
    
def handle_exception(core, exception):
        if exception.class_name == 'SyntaxError':
          raise SyntaxError(core)
        if exception.class_name == 'ReferenceError':
          raise ReferenceError(core)      