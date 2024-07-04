from .exceptions import CloudflareDetectionException
from .opponent import Opponent
from time import sleep, time

label_selector = "label"


def wait_till_document_is_ready(tab, wait_for_complete_page_load):
    
    if wait_for_complete_page_load:
        script = "return document.readyState === 'complete'"
    else:
        script = "return document.readyState === 'interactive' || document.readyState === 'complete'"

    while True:
        sleep(0.1)
        try:
            response = tab._run(tab.evaluate(script, await_promise=False))
            if response:
                break
        except Exception as e:
            print("An exception occurred", e)

def get_rayid(driver):
    ray = driver.get_text(".ray-id code")
    if ray:
        return ray


def get_iframe(driver):
    return driver.select("#turnstile-wrapper iframe", None)


def wait_till_cloudflare_leaves(driver, previous_ray_id):
    WAIT_TIME = 30
    start_time = time()
    while True:
        opponent = driver.get_bot_detected_by()
        if opponent != Opponent.CLOUDFLARE:
            return
        current_ray_id = get_rayid(driver)
        if current_ray_id:
            israychanged = current_ray_id != previous_ray_id

            if israychanged:

                WAIT_TIME = 12
                start_time = time()

                while True:

                    iframe = get_iframe(driver)

                    checkbox = iframe.select(label_selector, None)
                    takinglong = iframe.get_element_containing_text(
                        "is taking longer than expected", wait=None
                    )
                    if takinglong or checkbox:

                        # new captcha given
                        print("Cloudflare has detected us. Exiting ...")
                        raise CloudflareDetectionException()

                    elapsed_time = time() - start_time
                    if elapsed_time > WAIT_TIME:

                        print("Cloudflare has not given us a captcha. Exiting ...")

                        raise CloudflareDetectionException()

                    opponent = driver.get_bot_detected_by()
                    if opponent != Opponent.CLOUDFLARE:
                        return

                    sleep(1.79)

        elapsed_time = time() - start_time
        if elapsed_time > WAIT_TIME:
            print(
                "Cloudflare is taking too long to verify Captcha Submission. Exiting ..."
            )
            raise CloudflareDetectionException()

        sleep(0.83)

def solve_full_cf(driver):
            iframe = get_iframe(driver)
            while not iframe:
                opponent = driver.get_bot_detected_by()
                if opponent != Opponent.CLOUDFLARE:
                    return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)
                sleep(1)
                iframe = get_iframe(driver)
            previous_ray_id = get_rayid(driver)

            WAIT_TIME = 16
            start_time = time()

            while True:
                iframe = get_iframe(driver)
                while not iframe:
                    opponent = driver.get_bot_detected_by()
                    if opponent != Opponent.CLOUDFLARE:
                        return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)
                    sleep(1)
                    iframe = get_iframe(driver)

                checkbox = iframe.select(label_selector, None)
                if checkbox:
                    checkbox.click()
                    wait_till_cloudflare_leaves(driver, previous_ray_id)
                    return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)

                elapsed_time = time() - start_time
                if elapsed_time > WAIT_TIME:
                    print("Cloudflare has not given us a captcha. Exiting ...")
                    raise CloudflareDetectionException()
                sleep(1.79)    



def wait_till_cloudflare_leaves_widget(driver):
    WAIT_TIME = 30
    start_time = time()
    
    while True:
                    iframe = get_widget_iframe(driver)                
                    # success check 
                    if issuccess(iframe):
                        return

                    # failure 
                    if iframe.select('#fail[style="display: flex; visibility: visible;"]', None):
                        print("Cloudflare has detected us. Exiting ...")
                        raise CloudflareDetectionException()

                    # todo: remove checbox check
                    # checkbox = iframe.select(label_selector, None)        
                    takinglong = iframe.get_element_containing_text(
                        "is taking longer than expected", wait=None
                    )

                    if takinglong:

                        # new captcha given
                        print("Cloudflare has detected us. Exiting ...")
                        raise CloudflareDetectionException()

                    elapsed_time = time() - start_time
                    if elapsed_time > WAIT_TIME:
                        print("Cloudflare has detected us. Exiting ...")
                        raise CloudflareDetectionException()

                    sleep(0.83)

def issuccess(iframe):
    return iframe.select('#success[style="display: flex; visibility: visible;"]', None)

def get_widget_iframe(driver):
    return driver.select('[title="Widget containing a Cloudflare security challenge"]', None)

def solve_widget_cf(driver):
    iframe = get_widget_iframe(driver)
    while not iframe:
        opponent = driver.get_bot_detected_by()
        if opponent != Opponent.CLOUDFLARE:
            return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)
        sleep(1)
        iframe = get_widget_iframe(driver)

    WAIT_TIME = 16
    start_time = time()

    while True:
        iframe = get_widget_iframe(driver)
        while not iframe:
            opponent = driver.get_bot_detected_by()
            if opponent != Opponent.CLOUDFLARE:
                return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)
            sleep(1)
            iframe = get_widget_iframe(driver)

        if issuccess(iframe):
            return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)

        checkbox = iframe.select(label_selector, None)
        if checkbox:
            checkbox.click()
            wait_till_cloudflare_leaves_widget(driver)
            return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)

        elapsed_time = time() - start_time
        if elapsed_time > WAIT_TIME:
            print("Cloudflare has not given us a captcha. Exiting ...")
            raise CloudflareDetectionException()
        sleep(1.79)
def bypass_if_detected(driver, ):
    opponent = driver.get_bot_detected_by()
    if opponent == Opponent.CLOUDFLARE:
        if driver.select("#challenge-running", None):
            solve_full_cf(driver)
        else:
            solve_widget_cf(driver)
