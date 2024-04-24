import os
from .driver_utils import read_json, relative_path, write_json

def get_current_profile_path(profile): 
    profiles_path = f'profiles/{profile}/'
    return profiles_path

def save_cookies(driver, profile):
            current_profile_data = get_current_profile_path(profile) + 'profile.json'
            current_profile_data_path =  relative_path(current_profile_data, 0)

            cookies = driver.get_cookies()

            if type(cookies) is not list:
                cookies = cookies.get('cookies')
            write_json(cookies, current_profile_data_path)


def load_cookies(driver, profile):
    current_profile = get_current_profile_path(profile)
    current_profile_path = relative_path(current_profile, 0)

    if not os.path.exists(current_profile_path):
        os.makedirs(current_profile_path)

    current_profile_data = get_current_profile_path(profile) + 'profile.json'
    current_profile_data_path = relative_path(current_profile_data, 0)

    if not os.path.isfile(current_profile_data_path):
        return

    cookies = read_json(current_profile_data_path)
    driver.add_cookies(cookies)