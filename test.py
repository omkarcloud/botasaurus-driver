from botasaurus_driver import Driver

driver = Driver(
        headless=True
    )
# driver.get("https://www.freecodecamp.org/news/using-entity-framework-core-with-mongodb/", timeout=100)
# iframe = driver.get_iframe_by_link("www.youtube.com/embed") 
# # OR the following works as well
# # iframe = driver.select_iframe(".embed-wrapper iframe") 
# freecodecamp_youtube_subscribers_count = iframe.select(".ytp-title-expanded-subtitle").text
# print(freecodecamp_youtube_subscribers_count)
driver.close()