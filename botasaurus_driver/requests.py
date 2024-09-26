from requests.cookies import RequestsCookieJar
from requests.models import Response
from requests.utils import get_encoding_from_headers
from requests.structures import CaseInsensitiveDict
from .exceptions import DriverException

HTTP_STATUS_MESSAGES = {
    100: "Continue",
    101: "Switching Protocols",
    200: "OK",
    201: "Created",
    202: "Accepted",
    204: "No Content",
    300: "Multiple Choices",
    301: "Moved Permanently",
    302: "Found",
    304: "Not Modified",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout"
}

def get_status_message(status_code):
    return HTTP_STATUS_MESSAGES.get(status_code, "Unknown Status")

def _create_requests_cookie_jar_from_headers(cookie:dict):
        """
        Creates a RequestsCookieJar object from response headers.

        :param response_headers: A dictionary of response headers.
        :return: A RequestsCookieJar object containing the cookies.
        """
        cookie_jar = RequestsCookieJar()
        for key, morsel in cookie.items():
                        cookie_jar.set(
                            key,
                            morsel,
                        )
        return cookie_jar

def create_500_response(gr):
    response = Response()
              # Basic attributes
    response.status_code = 500
    response.url = gr["final_url"]
    response.request_url = gr["request_url"]
    reason = str(gr['error'])
    response.reason = reason

    hd = {}

    encoding ="utf-8"

    response.encoding = encoding
    response.headers = CaseInsensitiveDict(hd)
    response.cookies = _create_requests_cookie_jar_from_headers({})

    response._content = f'500 ({reason})'.encode(encoding)
    return response

def _convert_to_requests_response(gr, raise_fetch_exception):
        try:
          if gr['error']:
              if raise_fetch_exception:
                  raise DriverException(gr['error'])    
              return create_500_response(gr)
          response = Response()

          # Basic attributes
          response.status_code = gr['status_code']
          response.url = gr["final_url"]
          response.request_url = gr["request_url"]
          reason = gr["status_message"] or get_status_message(response.status_code)
          response.reason = reason

          hd = gr['headers']

          encoding = get_encoding_from_headers(hd)

          response.encoding = encoding
          response.headers = CaseInsensitiveDict(hd)
          response.cookies = _create_requests_cookie_jar_from_headers(gr["cookies"])
          if gr['result']:
              if encoding:
                  response._content = gr['result'].encode(encoding)
              else:
                  response._content = gr['result'].encode()
          return response
        except:
          print(gr)
          raise


template = r"""function fetchData(url) {
  return window.fetch(url, {
    "headers": {
        "priority": "u=0, i",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        ...args['headers'],
    },
  "referrer": "REF",
  "referrerPolicy": "strict-origin-when-cross-origin",
  "body": null,
  "method": "GET",
  "mode": "cors",
  "credentials": "include"
})
  .then(response => {
    return response.text().then(text => ({
      error: null,
      status_code: response.status,
      status_message: response.statusText,
      result: text,
      headers:[...response.headers.entries()].reduce((acc, [key, value]) => {
        acc[key] = value;
        return acc;
      }, {}),
      final_url: response.url,
      request_url: url,
      cookies: document.cookie.split(';').reduce((cookies, cookie) => {
        const [ name, value ] = cookie.split('=').map(c => c.trim());
        return { ...cookies, [name]: value };
        }, {}),
    }));
  })
  .catch(error => {
    return {
      final_url: url,
      request_url: url,    
      error: error.toString(),
      // result: error.message,
    };
  });
}
return fetchData("LINK")
"""


template_many = r"""function fetchData(url) {
  return window.fetch(url, {
    "headers": {
        "priority": "u=0, i",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        ...args['headers'],
    },
  "referrer": "REF",
  "referrerPolicy": "strict-origin-when-cross-origin",
  "body": null,
  "method": "GET",
  "mode": "cors",
  "credentials": "include"
})
  .then(response => {
    return response.text().then(text => ({
      error: null,
      status_code: response.status,
      status_message: response.statusText,
      result: text,
      headers:[...response.headers.entries()].reduce((acc, [key, value]) => {
        acc[key] = value;
        return acc;
      }, {}),
      final_url: response.url,
      request_url: url,
      cookies: document.cookie.split(';').reduce((cookies, cookie) => {
        const [ name, value ] = cookie.split('=').map(c => c.trim());
        return { ...cookies, [name]: value };
        }, {}),
    }));
  })
  .catch(error => {
    return {
      final_url: url,
      request_url: url,    
      error: error.toString(),
      // result: error.message,
    };
  });
}
return Promise.all(args['links'].map(fetchData)).catch(error => {
    return {
      error: error.toString(),
      // result: error.message,
    };
  })
"""

template_many_simultaneous = r"""
function fetchData(url) {
    return window.fetch(url, {
        "headers": {
            "priority": "u=0, i",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            ...args['headers'],
        },
        "referrer": "REF",
        "referrerPolicy": "strict-origin-when-cross-origin",
        "body": null,
        "method": "GET",
        "mode": "cors",
        "credentials": "include"
    })
        .then(response => {
            return response.text().then(text => ({
                error: null,
                status_code: response.status,
                status_message: response.statusText,
                result: text,
                headers: [...response.headers.entries()].reduce((acc, [key, value]) => {
                    acc[key] = value
                    return acc
                }, {}),
                final_url: response.url,
                request_url: url,
                cookies: document.cookie.split(';').reduce((cookies, cookie) => {
                    const [name, value] = cookie.split('=').map(c => c.trim())
                    return { ...cookies, [name]: value }
                }, {}),
            }))
        })
        .catch(error => {
            return {
                final_url: url,
                request_url: url,
                error: error.toString(),
                // result: error.message,
            }
        })
}



async function worker(urls, responses, errors) {
    let iterationCount = 0;
    while (urls.length > 0) {
        const url = urls.pop(); // Get a link from the list
        const response = await fetchData(url); // Fetch the URL

        const isSucess = response.status_code === 200 || response.status_code === 404;
        const hasNoRequestError = !response.error;
        const isValidResponse = isSucess && hasNoRequestError;
        if (isValidResponse) {
            responses.push(response); // Append if status is 200 or 404
            if (args['wait']) {
                await new Promise(resolve => setTimeout(resolve, args['wait'] * 1000));
            }
        } else {
            errors.push(url);
            if (response.error) {
                // Request Error Only, We can continue
            } else {
                return;
            }
        }
        iterationCount++;
    }
}


async function runWorkers(urls, workerCount) {
    const responses = []
    const errors = []
    const workers = []

    // Create workers and run them in parallel
    for (let i = 0; i < workerCount; i++) {
        workers.push(worker(urls, responses, errors))
    }
    // console.log('waiting')
    // Wait for all workers to complete
    await Promise.all(workers)
    // console.log('done')

    // Add any remaining URLs to the error list (if workers exit prematurely)

    if (urls.length) {
        errors.push(...urls)
    }

    return { responses, errors_links: errors }
}

return runWorkers(args['links'], args['workers'])
"""

def calculate_number_of_workers(urls, parallel):
        number_of_workers = parallel
        has_number_of_workers = number_of_workers is not None and not (number_of_workers == False)
        
        if not has_number_of_workers or number_of_workers <= 1:
            n = 1
        else:
            n = min(len(urls), int(number_of_workers))
        return n

def run_js_with_args(driver, fetchcode, args):
        if driver.native_fetch_name:
             fetchcode = fetchcode.replace("fetch(", driver.native_fetch_name + "(")
        else:
            print("To prevent custom fetch request detection, please call driver.prevent_fetch_spying() before visiting any page.")
        
        try:
          return driver.run_js(fetchcode, args)
        except Exception as e:
          if "Inspected target navigated or closed" in str(e):
            print("The page was closed or navigated away, Retrying")
            return run_js_with_args(driver, fetchcode, args)
          raise
        

class Request():
    def __init__(self, driver):
        self.driver = driver

    def get(self, url, headers=None, referer=None,):
        fetchcode = template.replace("LINK", url)
        
        if headers is None:
            fetchcode = fetchcode.replace("...args['headers'],", "")
        else:
            if not isinstance(headers, dict):
              raise TypeError("Headers must be a dictionary.")
            headers = {"headers":headers}
        
        if referer is None:
            fetchcode = fetchcode.replace('"referrer": "REF",', "")
        else:
            if not isinstance(referer, str):
              raise TypeError("referer must be a string.")
            fetchcode = fetchcode.replace("REF", referer)

        data = run_js_with_args(self.driver, fetchcode, headers)
        if data['error']:
            raise DriverException(data['error'])
        
        return _convert_to_requests_response(data, True)


    def get_many(self, urls, headers=None, referer=None,):
        fetchcode = template_many
        args = {}
        if headers is None:
            fetchcode = fetchcode.replace("...args['headers'],", "")
        else:
            if not isinstance(headers, dict):
              raise TypeError("Headers must be a dictionary.")
            args = {"headers":headers}
        
        if referer is None:
            fetchcode = fetchcode.replace('"referrer": "REF",', "")
        else:
            if not isinstance(referer, str):
              raise TypeError("referer must be a string.")
            fetchcode = fetchcode.replace("REF", referer)
        args['links'] = urls
        data = run_js_with_args(self.driver,fetchcode, args)

        if isinstance(data, dict) and data['error']:
          raise DriverException(data['error'])
        
        return [_convert_to_requests_response(x, False) for x in data]


    def get_many_simultaneous(self, urls, parallel=10, request_interval=None, headers=None, referer=None,):
        fetchcode = template_many_simultaneous
        args = {}
        if headers is None:
            fetchcode = fetchcode.replace("...args['headers'],", "")
        else:
            if not isinstance(headers, dict):
              raise TypeError("Headers must be a dictionary.")
            args = {"headers":headers}
        
        if referer is None:
            fetchcode = fetchcode.replace('"referrer": "REF",', "")
        else:
            if not isinstance(referer, str):
              raise TypeError("referer must be a string.")
            fetchcode = fetchcode.replace("REF", referer)
        
        # await new Promise(resolve => setTimeout(resolve, args['wait'] * 1000))
        n = calculate_number_of_workers(urls, parallel)

        args['links'] = urls
        args['workers'] = n
        args['wait'] = request_interval

        data = run_js_with_args(self.driver,fetchcode, args)

        responses = [_convert_to_requests_response(x, False) for x in data['responses']]
        errors_links  = data['errors_links']
        return responses, errors_links


