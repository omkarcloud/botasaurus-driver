def get_cookies(
    browser_context_id= None,
) :
    """
    Returns all browser cookies.

    :param browser_context_id: *(Optional)* Browser context to use when called on the browser endpoint.
    :returns: Array of cookie objects.
    """
    params = dict()
    if browser_context_id is not None:
        params["browserContextId"] = browser_context_id.to_json()
    cmd_dict = {
        "method": "Storage.getCookies",
        "params": params,
    }
    json = yield cmd_dict
    return json["cookies"]


def set_cookies(
    cookies,
    browser_context_id= None,
) :
    """
    Sets given cookies.

    :param cookies: Cookies to be set.
    :param browser_context_id: *(Optional)* Browser context to use when called on the browser endpoint.
    """
    params = dict()
    params["cookies"] = cookies
    if browser_context_id is not None:
        params["browserContextId"] = browser_context_id.to_json()
    cmd_dict = {
        "method": "Storage.setCookies",
        "params": params,
    }
    json = yield cmd_dict



def block_urls(
   urls
) :
    params = dict()
    params["urls"] = urls
    cmd_dict = {
        "method": "Network.setBlockedURLs",
        "params": params,
    }
    json = yield cmd_dict


def enable_network():
    params = dict()
    cmd_dict = {
        "method": "Network.enable",
        "params": params,
    }
    json = yield cmd_dict
