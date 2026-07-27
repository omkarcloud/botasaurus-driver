import random
import tempfile
import os
import socket
import sys
from ..driver_utils import convert_to_absolute_profile_path
from .env import is_vmish, is_docker
from ..exceptions import DriverException


def temp_profile_dir(port, parent_folder="bota"):
    """
    Creates a unique subfolder under the specified parent folder within the system's temporary directory.
    If the parent folder does not exist, it will be created.

    Returns the path to the created unique subfolder.
    """
    temp_dir = tempfile.gettempdir()
    parent_path = os.path.join(temp_dir, parent_folder)
    os.makedirs(parent_path, exist_ok=True)

    unique_folder = os.path.normpath(tempfile.mkdtemp(prefix=port, dir=parent_path))
    return unique_folder


__all__ = [
    "Config",
    "find_chrome_executable",
    "temp_profile_dir",
    "is_posix",
    "PathLike",
]


is_posix = sys.platform.startswith(("darwin", "cygwin", "linux", "linux2"))

PathLike = str
AUTO = None


def free_port():
    """Finds a random available port between 50000 and 54000"""
    while True:
        # using port's in these range avoid's bot detection datadome
        port = random.randint(50000, 55000)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as free_socket:
            try:
                free_socket.bind(('127.0.0.1', port))
                free_socket.listen(5)
                free_socket.close()
                return port
            except:
                continue



def clean_profile(profile):
    if profile:
        return str(profile).strip()



def should_force_no_sandbox():
    return is_docker


def unique_keys(all_urls):
    return list(dict.fromkeys(all_urls))


def create_local_proxy(auth_proxy):
    from botasaurus_proxy_authentication import create_proxy

    return create_proxy(auth_proxy)


def close_local_proxy(local_proxy):
    from botasaurus_proxy_authentication import close_proxy

    return close_proxy(local_proxy)


def create_extensions_string(extensions):
    if not isinstance(extensions, list):
        extensions = [extensions]
    extensions_str = ",".join(
        [extension.load(with_command_line_option=False) for extension in extensions]
    )
    return "--load-extension=" + extensions_str


def add_essential_options(options, profile, window_size, user_agent):

    if user_agent and user_agent != "REAL":
        from ..user_agent import UserAgentInstance, UserAgent

        if user_agent == UserAgent.RANDOM:
            if profile is not None:
                raise DriverException(
                    "When working with profiles, the user_agent must remain consistent and be generated based on the profile's unique hash. Instead of using a Random User Agent, use user_agent=UserAgent.HASHED."
                )
            else:
                user_agent = UserAgentInstance.get_random()
        elif user_agent == UserAgent.HASHED:
            user_agent = UserAgentInstance.get_hashed(profile)
        else:
            user_agent = user_agent

        options.add_argument(f"--user-agent={user_agent}")
    if window_size and window_size != "REAL":
        from ..window_size import WindowSizeInstance, WindowSize

        if window_size == WindowSize.RANDOM:
            if profile is not None:
                raise DriverException(
                    "When working with profiles, the window_size must remain consistent and be generated based on the profile's unique hash. Instead of using a Random Window Size, use window_size=WindowSize.HASHED."
                )
            else:
                window_size = WindowSizeInstance.get_random()
        elif window_size == WindowSize.HASHED:
            window_size = WindowSizeInstance.get_hashed(profile)
        else:
            window_size = window_size

        window_size = WindowSize.window_size_to_string(window_size)
        options.add_argument(f"--window-size={window_size}")

def validate_and_get_file(fl):
    is_windows = os.name == 'nt'
    if is_windows and not os.path.isfile(fl):
        chrome_path = os.path.join(fl, "chrome.exe")
        if os.path.isfile(chrome_path):
            return chrome_path
        else:
            if not os.path.exists(fl):
                raise FileNotFoundError(f"Provided path does not exist: {fl}")
            elif not os.path.isfile(fl):
                raise FileNotFoundError(f"Chrome Executable not found in the provided directory: {fl}")
            
            raise Exception(f"Invalid Chrome path provided: {fl}")
    elif not os.path.exists(fl):
        raise FileNotFoundError(f"Provided path does not exist: {fl}")
    
    return fl
class Config:
    """
    Config object
    """

    def __init__(
        self,
        headless=False,
        enable_xvfb_virtual_display=False,
        proxy=None,
        profile=None,
        tiny_profile=False,
        block_images=False,
        block_images_and_css=False,
        wait_for_complete_page_load=False,
        chrome_executable_path=None,
        extensions=[],
        arguments=[],
        remove_default_browser_check_argument = False,
        user_agent=None,
        window_size=None,
        lang=None,
        beep=False,
        host="127.0.0.1", 
        port=None,
    ):
        if tiny_profile and profile is None:
            raise ValueError("Profile must be given when using tiny profile")

        if enable_xvfb_virtual_display and headless:
            raise ValueError("Xvfb Virtual Display cannot be used while headless mode is enabled")

        self.headless = headless
        self.proxy = proxy
        self.enable_xvfb_virtual_display = enable_xvfb_virtual_display  # New attribute

        if self.proxy:
            self.local_proxy = create_local_proxy(self.proxy)
        else:
            self.local_proxy = None

        self.profile = clean_profile(profile)
        self.tiny_profile = tiny_profile

        self.block_images = block_images
        self.block_images_and_css = block_images_and_css

        self.wait_for_complete_page_load = wait_for_complete_page_load

        self.extensions = extensions

        self.arguments = arguments if arguments else []

        self.user_agent = user_agent
        self.window_size = window_size

        self.lang = lang
        self.beep = beep

        # Customizable host and port
        self.host = host
        self.port = port if port is not None else free_port()  # Use provided port or allocate a free one

        if self.tiny_profile or not self.profile:
            self.profile_directory = temp_profile_dir(str(self.port) + "_")
            self.is_temporary_profile = True
        else:
            self.profile_directory = convert_to_absolute_profile_path(self.profile)
            self.is_temporary_profile = False

        self.chrome_executable_path = validate_and_get_file(chrome_executable_path) if chrome_executable_path else find_chrome_executable()


        self.autodiscover_targets = True

        # Botasaurus Retry Data
        self.is_new = True

        self.retry_attempt = 0
        self.is_retry = False
        self.is_last_retry = False

        self._display = None

        add_essential_options(self, self.profile, self.window_size, self.user_agent)

        # other keyword args will be accessible by attribute
        super().__init__()
        self.default_arguments = [
            "--start-maximized",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-service-autorun",
            # Include `--no-default-browser-check` unless `remove_default_browser_check_argument` is True
            *([] if remove_default_browser_check_argument else ["--no-default-browser-check"]),
            "--homepage=about:blank",
            "--no-pings",
            "--password-store=basic",
            "--disable-infobars",
            "--disable-breakpad",
            "--disable-dev-shm-usage",
            "--disable-session-crashed-bubble",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-search-engine-choice-screen",

        ]

    @property
    def browser_args(self):
        return sorted(self.default_arguments + self.arguments)

    def close(self):
        if self.local_proxy:
            close_local_proxy(self.local_proxy)
        if self._display:
            self._display.stop()

    def __call__(self):
        args = self.default_arguments.copy()
        user_dr = "--user-data-dir=%s" % self.profile_directory

        if self.arguments:
            args.extend(self.arguments)
        # no need we are syncronous now

        if self.headless:
            args.append("--headless=new")
        else:
            if is_vmish or self.enable_xvfb_virtual_display:  # Modified condition
                from pyvirtualdisplay import Display

                try:
                    self._display = Display(visible=False, size=(1920, 1080))
                    self._display.start()
                except FileNotFoundError:
                    print(
                        'To run in headfull mode with xvfb virtual display, You need to install Xvfb. Please run "sudo apt-get install xvfb" in your terminal. (Note, We are currently running in headless mode)'
                    )
                    args.append("--headless=new")

        if should_force_no_sandbox():
            args.append("--no-sandbox")

        if self.host:
            host_str = "--remote-debugging-host=%s" % self.host
            args.append(host_str)

        if self.port:
            port_str = "--remote-debugging-port=%s" % self.port
            args.append(port_str)

        if self.lang:
            args.append(f"--lang={self.lang}")

        if self.extensions:
            args.append(create_extensions_string(self.extensions))

        if self.local_proxy:
            args.append(f"--proxy-server=" + self.local_proxy)

        args.append(user_dr)
        args = unique_keys(args)
        return args


    def add_argument(self, arg: str):

        self.arguments.append(arg)

    def __repr__(self):
        s = f"{self.__class__.__name__}"
        for k, v in ({**self.__dict__, **self.__class__.__dict__}).items():
            if k[0] == "_":
                continue
            if not v:
                continue
            if isinstance(v, property):
                v = getattr(self, k)
            if callable(v):
                continue
            s += f"\n\t{k} = {v}"
        return s



def get_linux_executable_path():
    import shutil

    for executable in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "google-chrome-beta",
        "google-chrome-dev",
                "chrome",):
        path = shutil.which(executable)
        if path is not None:
            return path

    raise FileNotFoundError(
        "You don't have Google Chrome installed on your Linux system. Please install it by visiting https://www.google.com/chrome/."
    )


def find_chrome_executable():
    """
    Determines the path to the Google Chrome executable on the system based on the platform.

    :return: Full path to the Google Chrome executable if found, otherwise None.
    """
    if sys.platform.startswith("linux"):
        return (
            get_linux_executable_path()
        )  # This function already exists in your code and finds Chrome on Linux.
    elif sys.platform.startswith("darwin"):
        possible_paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        for path in possible_paths:
            if os.path.isfile(path):
                return path

        raise FileNotFoundError(
            "You don't have Google Chrome installed on your MacOS. Please install it by visiting https://www.google.com/chrome/."
        )
        # Path for Google Chrome on macOS.
    elif sys.platform.startswith("win"):
        PROGRAMFILES = f"{os.environ.get('PROGRAMW6432') or os.environ.get('PROGRAMFILES')}\\Google\\Chrome\\Application\\chrome.exe"
        if os.path.exists(PROGRAMFILES):
            path = PROGRAMFILES
        else:
            PROGRAMFILESX86 = f"{os.environ.get('PROGRAMFILES(X86)')}\\Google\\Chrome\\Application\\chrome.exe"
            if os.path.exists(PROGRAMFILESX86):
                path = PROGRAMFILESX86
            else:
                LOCALPATH = f"{os.environ.get('LOCALAPPDATA')}\\Google\\Chrome\\Application\\chrome.exe"
                if os.path.exists(LOCALPATH):
                    path = LOCALPATH
                else:
                    path = None
        if not path:
            raise FileNotFoundError(
                "You don't have Google Chrome installed on your Windows system. Please install it by visiting https://www.google.com/chrome/."
            )
        else:
            return path

    return None
