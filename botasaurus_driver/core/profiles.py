import tempfile
from time import sleep
import shutil
import os

def get_subfolders(parent_folder="bota"):
    """
    Returns a list of all subfolders within the specified parent folder in the system's temporary directory.
    """
    temp_dir = tempfile.gettempdir()
    parent_path = os.path.join(temp_dir, parent_folder)
    if not os.path.exists(parent_path):
        return []
    subfolders = [folder for folder in os.listdir(parent_path)]
    return subfolders

def delete_profile(user_data_dir):
        for attempt in range(5):
            try:
                shutil.rmtree(user_data_dir, ignore_errors=False)
            except FileNotFoundError as e:
                break
            except (PermissionError, OSError) as e:
                if attempt == 4:
                    break
                sleep(0.15)
                continue
            
def is_chrome_running_on_ports(ports):
    """
    Checks if Chrome is running on any of the specified ports.
    Returns a set of ports where Chrome is running.
    """
    import psutil
    running_ports = set()
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            if 'chrome' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline:
                    for port in ports:
                        if any(f'--remote-debugging-port={port}' in arg for arg in cmdline):
                            running_ports.add(port)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return running_ports

def get_target_folders(instances):
    folders = get_subfolders()
    if not folders:
      return []
    
    whitelist = set(x.base_folder_name for x in instances)  # Converting the whitelist to a set

    # Get folders that are not in the whitelist
    non_whitelisted_folders = [folder for folder in folders if folder not in whitelist]
    return non_whitelisted_folders

def check_and_delete_dead_profiles(non_whitelisted_folders):
    
    # Get port numbers from folder names
    ports = set()
    for folder in non_whitelisted_folders:
        try:
            port = int(folder.split('_')[0])
            ports.add(port)
        except ValueError:
            # Folder name does not match the expected format, skip it
            continue

    # Check if Chrome is running on any of the ports
    running_ports = is_chrome_running_on_ports(ports)
    
    # Delete folders where Chrome is not running
    temp_dir = tempfile.gettempdir()
    parent_path = os.path.join(temp_dir, "bota")
    for folder in non_whitelisted_folders:
        try:
            port = int(folder.split('_')[0])
            if port not in running_ports:
                folder_path = os.path.join(parent_path, folder)
                delete_profile(folder_path)
                # print(f"Deleted folder: {folder_path}")
        except ValueError:
            # Folder name does not match the expected format, skip it
            continue

def run_check_and_delete_in_thread(folders):
    from threading import Thread
    thread = Thread(target=check_and_delete_dead_profiles, args=(folders,), daemon=True)
    thread.start()
