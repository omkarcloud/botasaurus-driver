from .exceptions import CloudflareDetectionException
from .opponent import Opponent
from time import sleep, time

label_selector = "label"

def wait_till_document_is_ready(tab, wait_for_complete_page_load):
    max_wait_time = 30
    start_time = time()
    
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
        
        elapsed_time = time() - start_time
        if elapsed_time > max_wait_time:
            raise TimeoutError("Document did not become ready within 30 seconds")

def istakinglong(iframe):
    return "is taking longer than expected" in iframe.get_element_at_point(main_x,main_y,  wait=None).text

def get_rayid(driver):
    ray = driver.select(".ray-id code")
    if ray:
        return ray.text
main_x =3
main_y =3

def get_iframe(driver):
    return driver.get_iframe_by_link("challenges.cloudflare.com", wait=None)


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
                    if iframe:
                        checkbox = iframe.get_element_at_point(main_x,main_y, label_selector, wait=None)
                        takinglong = istakinglong(iframe)
                        if takinglong or checkbox:

                            # new captcha given
                            print("Cloudflare has detected us. Exiting ...")
                            raise CloudflareDetectionException()

                    opponent = driver.get_bot_detected_by()
                    if opponent != Opponent.CLOUDFLARE:
                        return

                    elapsed_time = time() - start_time
                    if elapsed_time > WAIT_TIME:

                        print("Cloudflare has not given us a captcha. Exiting ...")

                        raise CloudflareDetectionException()


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

                checkbox = iframe.get_element_at_point(main_x,main_y, label_selector, wait=None)
                if checkbox:
                    raise CloudflareDetectionException()
                    # print('aa')
                    checkbox.humane_click()
                    wait_till_cloudflare_leaves(driver, previous_ray_id)
                    return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)

                elapsed_time = time() - start_time
                if elapsed_time > WAIT_TIME:
                    print("Cloudflare has not given us a captcha. Exiting ...")
                    raise CloudflareDetectionException()
                sleep(1.79)


def get_widget_iframe(driver):
    return driver.get_iframe_by_link("challenges.cloudflare.com", wait=None)

def wait_for_widget_iframe(driver):
    iframe = get_widget_iframe(driver)
    while not iframe:
        sleep(1)
        iframe = get_widget_iframe(driver)
    return iframe

def wait_till_cloudflare_leaves_widget(driver):
    WAIT_TIME = 30
    start_time = time()
    
    while True:
                    iframe = get_widget_iframe(driver)
                    if iframe:
                        # success check 
                        if issuccess(iframe):
                            return

                        # failure 
                        if isfailure(iframe):
                            print("Cloudflare has detected us. Exiting ...")
                            raise CloudflareDetectionException()

                        # todo: remove checbox check
                        # checkbox = iframe.select(label_selector, None)        
                        takinglong = istakinglong(iframe)

                        if takinglong:

                            # new captcha given
                            print("Cloudflare has detected us. Exiting ...")
                            raise CloudflareDetectionException()

                    opponent = driver.get_bot_detected_by()
                    if opponent != Opponent.CLOUDFLARE:
                        return

                    elapsed_time = time() - start_time
                    if elapsed_time > WAIT_TIME:
                        print("Cloudflare has detected us. Exiting ...")
                        raise CloudflareDetectionException()

                    sleep(0.83)


def issuccess(iframe):
    return iframe.get_element_at_point(main_x,main_y, '#success[style="display: flex; visibility: visible;"]', wait=None)

def isfailure(iframe):
    return iframe.get_element_at_point(main_x,main_y, '#fail[style="display: flex; visibility: visible;"]', wait=None)

def solve_widget_cf(driver):
    iframe = wait_for_widget_iframe(driver)

    WAIT_TIME = 16
    start_time = time()

    while True:
        iframe = wait_for_widget_iframe(driver)

        if issuccess(iframe):
            return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)

        checkbox = iframe.get_element_at_point(main_x,main_y, label_selector, wait=None)
        if checkbox:
            checkbox.humane_click()
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
        if driver.select('script[data-cf-beacon]', None):
            solve_widget_cf(driver)
        else:
            solve_full_cf(driver)