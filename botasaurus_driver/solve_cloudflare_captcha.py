from .driver_utils import with_human_mode_hidden_cursor
from .exceptions import CloudflareDetectionException, ShadowRootClosedException
from .opponent import Opponent
from time import sleep, time
import random


def click_restoring_human_behaviour(driver, checkbox):
    def fn():
        checkbox.move_mouse_here(is_jump=True)
        checkbox.click(skip_move=True)
    with_human_mode_hidden_cursor(driver, fn)

def click_point_restoring_human_behaviour(driver, x,y):
    def fn():
        driver.move_mouse_to_point(is_jump=True)
        driver.click_at_point(x,y,skip_move=True)
    with_human_mode_hidden_cursor(driver, fn)


def wait_till_document_is_ready(tab, wait_for_complete_page_load, timeout = 60):
    start_time = time()
    
    if wait_for_complete_page_load:
        script = "return document.readyState === 'complete'"
    else:
        script = "return document.readyState === 'interactive' || document.readyState === 'complete'"

    while True:
        sleep(0.1)
        try:
            response = tab.evaluate(script, await_promise=False)
            if response:
                break
        except Exception as e:
            print("An exception occurred", e)
        
        elapsed_time = time() - start_time
        if elapsed_time > timeout:
            raise TimeoutError(f"Document did not become ready within {timeout} seconds")

def is_taking_long(iframe):
    return iframe.run_js("(el) => (el.innerText || el.textContent).includes('is taking longer than expected')")

def get_rayid(driver):
    ray = driver.select(".ray-id code")
    if ray:
        return ray.text
    
def get_turnstile_parent(driver):
            turnstile = driver.select('[name="cf-turnstile-response"]:not(#cf-invisible-turnstile [name="cf-turnstile-response"])', wait=None)
            if turnstile:
                return turnstile.parent
            return None

def get_iframe_tab(driver):
            shadow_root_element = get_turnstile_parent(driver)
            if shadow_root_element:
                iframe_tab = shadow_root_element.get_shadow_root()
                return iframe_tab
def get_iframe_content(driver):
                iframe_tab = get_iframe_tab(driver)
                if iframe_tab:
                    content_el = iframe_tab.get_shadow_root()
                    return content_el


def get_widget_iframe_via_get_iframe_by_link(driver):
        itab = driver.get_iframe_by_link("challenges.cloudflare.com", wait=8)
        if itab:
        #   Fix the rect which is not there if we find via driver.get_iframe_by_link("challenges.cloudflare.com")
          itab._get_bounding_rect_with_iframe_offset = lambda: get_turnstile_parent(driver)._get_bounding_rect_with_iframe_offset()
          return itab.get_shadow_root()
        
        
def get_widget_iframe(driver):
    try:
        shadow_root_element = get_turnstile_parent(driver)
        if shadow_root_element:
            iframe_tab = shadow_root_element.get_shadow_root()
            if iframe_tab:
                content_el = iframe_tab.get_shadow_root()
                return content_el
    except ShadowRootClosedException:
        content_el = get_widget_iframe_via_get_iframe_by_link(driver)
        if not content_el:
             raise
        return content_el
    except:
        return None


def wait_till_cloudflare_leaves(driver, previous_ray_id):
    WAIT_TIME = 30
    start_time = time()
    while True:
        if not driver.is_bot_detected_by_cloudflare():
            return
        current_ray_id = get_rayid(driver)
        if current_ray_id:
            israychanged = current_ray_id != previous_ray_id

            if israychanged:

                WAIT_TIME = 12
                start_time = time()

                while True:
                    if not driver.is_bot_detected_by_cloudflare():
                        return
                    
                    iframe = get_iframe_content(driver)
                    if iframe:
                        checkbox = get_checkbox(iframe)
                        if checkbox or is_taking_long(iframe):
                            # new captcha given
                            print("Cloudflare has detected us. Exiting ...")
                            raise CloudflareDetectionException()


                    elapsed_time = time() - start_time
                    if elapsed_time > WAIT_TIME:
                        print("Cloudflare has not given us a captcha. Exiting ...")
                        raise CloudflareDetectionException()


                    sleep(1)

        elapsed_time = time() - start_time
        if elapsed_time > WAIT_TIME:
            print(
                "Cloudflare is taking too long to verify Captcha Submission. Exiting ..."
            )
            raise CloudflareDetectionException()

        sleep(1)

def solve_full_cf(driver):
            iframe = get_iframe_content(driver)
            while not iframe:
                if not driver.is_bot_detected_by_cloudflare():
                    return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)
                sleep(0.75)
                iframe = get_iframe_content(driver)
            previous_ray_id = get_rayid(driver)

            WAIT_TIME = 16
            start_time = time()

            while True:
                iframe = get_iframe_content(driver)
                while not iframe:
                    if not driver.is_bot_detected_by_cloudflare():
                        return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)
                    sleep(0.75)
                    iframe = get_iframe_content(driver)

                checkbox = get_checkbox(iframe)
                if checkbox:
                    click_restoring_human_behaviour(driver, checkbox)
                    wait_till_cloudflare_leaves(driver, previous_ray_id)
                    return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)

                elapsed_time = time() - start_time
                if elapsed_time > WAIT_TIME:
                    print("Cloudflare has not given us a captcha. Exiting ...")
                    raise CloudflareDetectionException()
                sleep(1)

def get_checkbox(iframe):
    return iframe.select("input", wait=None)


def wait_for_widget_iframe(driver):
    iframe = get_widget_iframe(driver)
    while not iframe:
        if not driver.is_bot_detected_by_cloudflare():
            return "bot_not_detected"
        sleep(0.75)
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


                        if is_taking_long(iframe):
                            # new captcha given
                            print("Cloudflare has detected us. Exiting ...")
                            raise CloudflareDetectionException()

                    if not driver.is_bot_detected_by_cloudflare():
                        return

                    elapsed_time = time() - start_time
                    if elapsed_time > WAIT_TIME:
                        print("Cloudflare has detected us. Exiting ...")
                        raise CloudflareDetectionException()

                    sleep(1)


def issuccess(iframe):
    return iframe.select('#success[style="display: grid; visibility: visible;"]' , wait=None)

def isfailure(iframe):
    return iframe.select('#fail[style="display: grid; visibility: visible;"]', wait=None)

def perform_click(driver, el):
    rect = el._get_bounding_rect_with_iframe_offset()
    x_center = rect.x + 30
    x = x_center + random.randint(-5, 5)
    y_center = rect.y + (rect.height / 2)
    y = y_center   + random.randint(-5, 5)

    return click_point_restoring_human_behaviour(driver, x,y)

def click_clf_checkbox_widget(driver):
    el = get_turnstile_parent(driver)
    if el:
        return perform_click(driver, el)

def solve_widget_cf(driver):
    try:
      iframe = wait_for_widget_iframe(driver)
      if iframe == "bot_not_detected":
           return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)
      
    except ShadowRootClosedException:
      # Let it load
      sleep(0.75)
      return click_clf_checkbox_widget(driver)

    WAIT_TIME = 16
    start_time = time()

    while True:
        iframe = wait_for_widget_iframe(driver)
        if iframe == "bot_not_detected":
           return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)
        if issuccess(iframe):
            return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)

        checkbox = get_checkbox(iframe)
        if checkbox:
            click_restoring_human_behaviour(driver, checkbox)
            wait_till_cloudflare_leaves_widget(driver)
            return wait_till_document_is_ready(driver._tab, driver.config.wait_for_complete_page_load)

        elapsed_time = time() - start_time
        if elapsed_time > WAIT_TIME:
            print("Cloudflare has not given us a captcha. Exiting ...")
            raise CloudflareDetectionException()
        sleep(1)

def bypass_if_detected(driver):
    opponent = driver.get_bot_detected_by()
    if opponent == Opponent.CLOUDFLARE:
        if driver.title == "Just a moment...":
            solve_full_cf(driver)
        else:
            solve_widget_cf(driver)