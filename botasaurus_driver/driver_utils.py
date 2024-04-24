import json
import os
from time import sleep

from .exceptions import DriverException, GoogleCookieConsentException



def read_json(path):
    with open(path, 'r', encoding="utf-8") as fp:
        data = json.load(fp)
        return data

        
def write_json(data, path,  indent=4):
    with open(path, 'w', encoding="utf-8") as fp:
        json.dump(data, fp, indent=indent)    

def sleep_forever():
    print("Sleeping Forever")
    while True:
        sleep(100)


def sleep_for_n_seconds(n):
    if n is not None and n != 0:
        print(f"Sleeping for {n} seconds...")
        sleep(n)

def verify_cookies(driver):
    def check_page():
        return "NID" in driver.get_cookies_dict()

    time = 0
    WAIT = 8

    while time < WAIT:
        if check_page():
            return True

        sleep_time = 0.1
        time += sleep_time
        sleep(sleep_time)

    raise GoogleCookieConsentException()


def perform_accept_google_cookies_action(driver):
    input_el = driver.select('[role="combobox"], [role="search"]', 16)
    if input_el is None:
        raise DriverException("Failed to load google.com")
    else:
        accept_cookies_btn = driver.select("button#L2AGLb", None)
        if accept_cookies_btn is None:
            pass
        else:
            accept_cookies_btn.click()
            verify_cookies(driver)


def relative_path(path, goback=0):
    levels = [".."] * (goback + -1)
    return os.path.abspath(os.path.join(os.getcwd(), *levels, path.strip()))


def convert_to_absolute_path(path):
    """
    Converts a relative path to an absolute path.

    Args:
        path (str): The path to be converted.
        base_dir (str, optional): The base directory to use for relative paths.
                                  If not provided, the current working directory is used.

    Returns:
        str: The absolute path.
    """
    # Use current working directory if base_dir is not provided
    # If the input path is already absolute, return it
    if os.path.isabs(path):
        return path

    # Otherwise, join the base_dir and path
    return relative_path(path)



def is_slash_not_in_filename(filename):
    return "/" not in filename and "\\" not in filename


def convert_to_absolute_profile_path(profile):
    """
    Converts a relative path to an absolute path.

    Args:
        path (str): The path to be converted.
        base_dir (str, optional): The base directory to use for relative paths.
                                  If not provided, the current working directory is used.

    Returns:
        str: The absolute path.
    """
    if is_slash_not_in_filename(profile):
        PROFILES_PATH = 'profiles'
        create_directory_if_not_exists("profiles/")
        PATH = f'{PROFILES_PATH}/{profile}'
        path = relative_path(PATH, 0)
        return path
    
    return convert_to_absolute_path(profile)

def create_directory_if_not_exists(passed_path):
    dir_path = relative_path(passed_path, 0)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

def ensure_supports_file_upload(el):
    if el._elem.node.node_name.lower() != "input" or el.get_attribute("type") != "file":
        raise DriverException(f"Element {el} does not support file uploads.")


def ensure_supports_multiple_upload(el):
    ensure_supports_file_upload(el)
    if not ("multiple" in el._elem._attrs):
        raise DriverException(f"Element {el} does not support multiple file uploads.")

    if el._elem._attrs["multiple"] == "f" or el._elem._attrs["multiple"] == "false":
        raise DriverException(f"Element {el} does not support multiple file uploads.")


def ensure_video_element(el):
    if el._elem.node.node_name.lower() != "video":
        raise DriverException(
            f"Element '{el}' is not a video element. Recording is only supported on video elements."
        )



def create_screenshot_filename(filename):
    filename = filename.strip()
    if not filename.endswith(".png"):
        filename = filename + ".png"
    if is_slash_not_in_filename(filename):
        create_directory_if_not_exists("output/")
        create_directory_if_not_exists("output/screenshots/")
        filename = f"./output/screenshots/{filename}"
        return relative_path(filename, 0), filename 
    else:
        return convert_to_absolute_path(filename), convert_to_absolute_path(filename)


def get_download_directory():
    create_directory_if_not_exists("output/")
    create_directory_if_not_exists("output/downloads/")
    return relative_path("./output/downloads/", 0)

def get_download_filename(filename):
    return os.path.abspath(os.path.join("./output/downloads/", filename.strip())), f"./output/downloads/{filename}"

def create_video_filename(filename):
    filename = filename.strip()

    if not filename.endswith(".mp4"):
        filename = filename + ".mp4"
    return filename
