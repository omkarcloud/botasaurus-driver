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


def wait_till_cloudflare_leaves(driver, previous_ray_id, raise_exception):
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
                        if raise_exception:
                            raise CloudflareDetectionException()
                        return

                    elapsed_time = time() - start_time
                    if elapsed_time > WAIT_TIME:

                        print("Cloudflare has not given us a captcha. Exiting ...")

                        if raise_exception:
                            raise CloudflareDetectionException()
                        return

                    opponent = driver.get_bot_detected_by()
                    if opponent != Opponent.CLOUDFLARE:
                        return

                    sleep(1.79)

        elapsed_time = time() - start_time
        if elapsed_time > WAIT_TIME:
            print(
                "Cloudflare is taking too long to verify Captcha Submission. Exiting ..."
            )
            if raise_exception:
                raise CloudflareDetectionException()

            return

        sleep(0.83)


def bypass_if_detected(driver, raise_exception=True):
    opponent = driver.get_bot_detected_by()
    if opponent == Opponent.CLOUDFLARE:
        iframe = get_iframe(driver)
        while not iframe:
            opponent = driver.get_bot_detected_by()
            if opponent != Opponent.CLOUDFLARE:
                return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)
            sleep(1)
            iframe = get_iframe(driver)
        previous_ray_id = get_rayid(driver)

        WAIT_TIME = 8
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
                wait_till_cloudflare_leaves(driver, previous_ray_id, raise_exception)
                return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)

            elapsed_time = time() - start_time
            if elapsed_time > WAIT_TIME:
                print("Cloudflare has not given us a captcha. Exiting ...")

                if raise_exception:
                    raise CloudflareDetectionException()

                return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)
            sleep(1.79)