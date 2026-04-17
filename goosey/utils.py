#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Untitled Goose Tool: Utils!
"""

import asyncio
import configparser
import darkdetect
import json
import logging
import os
import sys
import getpass
import pyAesCrypt
import io
import pytz

from colored import stylize, attr, fg
from datetime import datetime, timedelta, date
from logging import handlers
import dateutil.parser

if sys.platform == 'win32':
    import msvcrt
else:
    import fcntl

utc = pytz.UTC

# Custom logging from https://stackoverflow.com/questions/384076/how-can-i-color-python-logging-output
class CustomFormatter(logging.Formatter):
    """Logging Formatter to add colors and count warning / errors"""

    blue = "\x1b[34;21m"
    grey = "\x1b[38;21m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"

    # Until we import a fancier library like colorama or clrprint, opt for no colors on non-posix terminals
    if os.name != 'posix':
        blue = ""
        grey = ""
        yellow = ""
        red = ""
        bold_red = ""
        reset = ""

    format = "%(asctime)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    if sys.version_info >= (3,12):
        # taskName key is only available after python 3.12
        format = "%(asctime)s - %(taskName)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"

    FORMATS = {
        logging.DEBUG: blue + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

class LogLevelFilter(logging.Filter):
    def __init__(self, level):
        self.level = level

    def filter(self, record):
        return record.levelno == self.level

def setup_logger(name, debug, formatter='cli') -> None:
    """Helper function to set up logger.

    :param name: Logger name to grab
    :type name: str
    :param debug: Flag indicating if debug mode is set.
    :type debug: bool
    :param formatter: Custom formatter to use.
    :type formatter: str
    :return: None
    :rtype: None
    """
    debug_log = "debug.log"
    error_log = "error.log"

    logger = logging.getLogger(name)
    format = "%(asctime)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    if sys.version_info >= (3,12):
        # taskName key is only available after python 3.12
        format = "%(asctime)s - %(taskName)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    file_formatter = logging.Formatter(format)

    debug_fh = logging.handlers.WatchedFileHandler(debug_log)
    debug_fh.setFormatter(file_formatter)
    debug_fh.addFilter(LogLevelFilter(logging.DEBUG))
    debug_fh.setLevel(logging.DEBUG)

    error_fh = logging.handlers.WatchedFileHandler(error_log)
    error_fh.setFormatter(file_formatter)
    error_fh.addFilter(LogLevelFilter(logging.ERROR))
    error_fh.setLevel(logging.ERROR)

    logger.addHandler(debug_fh)
    logger.addHandler(error_fh)


    if debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    # create console handler with a higher log level
    ch = logging.StreamHandler()

    if debug:
        ch.setLevel(logging.DEBUG)
    else:
        ch.setLevel(logging.INFO)

    if formatter == 'cli':
        ch.setFormatter(CustomFormatter())
    logger.addHandler(ch)

    return logger

logger = setup_logger(__name__, debug=False)

class obj(object):
    def __init__(self, dict_):
        self.__dict__.update(dict_)

def dict2obj(d):
    return json.loads(json.dumps(d), object_hook=obj)

def build_date_range(start_date, end_date):
    res = []
    res.append(start_date)

    while start_date != end_date:
        res.append((datetime.strptime(start_date,"%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d"))
        start_date = (datetime.strptime(start_date,"%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    return res

def build_date_tuples(chunk_size=26, start_date=None, end_date=None):
    """Helper function to chunk last 364 days into 14 chunks

    :return: A list of the checkpoint dates when chunking the last 364 days.
    :rtype: List
    """

    ret = []

    if start_date and end_date:
        start_date = datetime.strptime(start_date,"%Y-%m-%d")
        diff = end_date - start_date
        if diff.days > 26:
            ret.append(end_date.strftime("%Y-%m-%d"))
            while end_date.date() > start_date.date():
                ret.append((end_date - timedelta(days=26)).strftime("%Y-%m-%d"))
                end_date = end_date - timedelta(days=26)
        else:
            ret.append(end_date.strftime("%Y-%m-%d"))
            ret.append(start_date.strftime("%Y-%m-%d"))
    else:
        for i in range(0, 365, chunk_size):
            ret.append((datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"))
    return ret[::-1]

def findkeys(node, kv):
    if isinstance(node, list):
        for i in node:
            for x in findkeys(i, kv):
                yield x
    elif isinstance(node, dict):
        if kv in node:
            yield node[kv]
        for j in node.values():
            for x in findkeys(j, kv):
                yield x

def search_results(values, lookup):
    for k in values:
        if any(lookup in str(s) for s in k.values()):
            return k
    return None

def config_get(conf, section: str, option: str, logger=None, default=None):
    """Helper function for getting config options from a configparser.

    :param conf: configparser item after reading a config file or string.
    :type conf: configparser.ConfigParser
    :param section: section in config file
    :type section: str
    :param option: option item in config file
    :type option: str
    :param logger: logging context
    :type logger: logger
    :param default: default to return
    :type default: any
    :return: config item based on section and option
    :rtype: any
    """
    r = None
    try:
        r = conf.get(section, option)
    except configparser.NoSectionError as e:
        err = f"Missing section in config file: {section}. Proceeding."
        if logger:
            logger.warning(err)
        else:
            print(err)
    except configparser.NoOptionError as e:
        if option:
            err = f"Missing option in config file: {option}. Proceeding."
            logger.warning(err) if logger else print(err)
    except Exception as e:
        err = f"Unknown exception while parsing config file: {str(e)}"
        logger.warning(err) if logger else print(err)
    return r

def check_output_dir(output_dir, logger):
    if not os.path.exists(output_dir):
        logger.info(f'Output directory "{output_dir}" does not exist. Attempting to create.')
        try:
            os.makedirs(output_dir)
        except Exception as e:
            logger.error(f'Error while attempting to create output directory {output_dir}: {str(e)}')
            raise
    elif not os.path.isdir(output_dir):
        logger.error(f'{output_dir} exists but is not a directory or you do not have permissions to access. Exiting.')
        sys.exit(1)


async def google_api_call_with_retry(service_call, logger, retries=5, delay=60):
    """
    Execute a Google API call with retry logic for rate limiting and transient errors.

    Args:
        service_call: A callable that executes the API request (e.g., lambda: service.users().list(...).execute())
        logger: Logger instance
        retries: Number of retries
        delay: Delay in seconds between retries

    Returns:
        The API response dict
    """
    from googleapiclient.errors import HttpError
    for attempt in range(retries):
        try:
            return service_call()
        except HttpError as e:
            if e.resp.status == 429:
                logger.info(f"Rate limited. Sleeping for {delay} seconds before retry {attempt+1}/{retries}...")
                await asyncio.sleep(delay)
            elif e.resp.status == 403:
                logger.warning(f"Permission denied: {str(e)}")
                return None
            elif e.resp.status == 401:
                logger.error(f"Unauthorized: {str(e)}. Please re-auth.")
                sys.exit(1)
            elif e.resp.status >= 500:
                logger.warning(f"Server error ({e.resp.status}). Retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"HTTP error {e.resp.status}: {str(e)}")
                return None
        except Exception as e:
            logger.error(f"Error on API call: {str(e)}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
            else:
                return None
    return None


async def google_paginated_results(service_request, logger, retries=5, delay=60):
    """
    Handle Google API pagination using nextPageToken.

    Args:
        service_request: Initial API request object (not yet executed)
        logger: Logger instance
        retries: Number of retries per page
        delay: Delay in seconds between retries

    Yields:
        Individual items from paginated results
    """
    from googleapiclient.errors import HttpError
    request = service_request
    while request is not None:
        try:
            response = request.execute()
        except HttpError as e:
            if e.resp.status == 429:
                logger.info(f"Rate limited during pagination. Sleeping for {delay}s...")
                await asyncio.sleep(delay)
                continue
            elif e.resp.status == 401:
                logger.error(f"Unauthorized: {str(e)}. Please re-auth.")
                sys.exit(1)
            else:
                logger.error(f"HTTP error during pagination: {str(e)}")
                break
        except Exception as e:
            logger.error(f"Error during pagination: {str(e)}")
            break

        # Google APIs use various keys for their result arrays
        for key in ['users', 'groups', 'members', 'items', 'activities',
                     'roles', 'roleAssignments', 'domains', 'orgUnits',
                     'chromeosdevices', 'mobiledevices', 'tokens',
                     'alerts', 'usageReports', 'messages', 'filters',
                     'delegates', 'forwardingAddresses', 'sendAs',
                     'value', 'resources']:
            if key in response:
                for item in response[key]:
                    yield item
                break
        else:
            # If no known key, yield the whole response
            yield response

        # Get next page
        if 'nextPageToken' in response:
            # Build the next request with the page token
            request = service_request
            # We need to rebuild the request with the new page token
            # This is handled by the list_next pattern in Google API client
            break  # We'll use list_next pattern instead

        request = None


async def dump_google_api_results(service, request_builder, outfile, logger, key=None):
    """
    Paginate through Google API results and dump to a file.

    Args:
        service: The Google API service object (for list_next calls)
        request_builder: Initial request (e.g., service.users().list(...))
        outfile: Output file path
        logger: Logger instance
        key: The key in the response that contains the items (e.g., 'users', 'groups')
    """
    from googleapiclient.errors import HttpError
    request = request_builder
    total_items = 0
    retries = 5
    delay = 60

    while request is not None:
        for attempt in range(retries):
            try:
                response = request.execute()
                break
            except HttpError as e:
                if e.resp.status == 429:
                    logger.info(f"Rate limited. Sleeping for {delay}s (attempt {attempt+1}/{retries})...")
                    await asyncio.sleep(delay)
                elif e.resp.status == 401:
                    logger.error(f"Unauthorized: {str(e)}. Please re-auth.")
                    sys.exit(1)
                elif e.resp.status >= 500:
                    logger.warning(f"Server error ({e.resp.status}). Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"HTTP error {e.resp.status}: {str(e)}")
                    return total_items
            except Exception as e:
                logger.error(f"Error: {str(e)}")
                return total_items
        else:
            logger.error("Max retries reached during pagination.")
            return total_items

        items = []
        if key and key in response:
            items = response[key]
        elif not key:
            # Try common Google API result keys
            for k in ['users', 'groups', 'members', 'items', 'activities',
                       'roles', 'roleAssignments', 'domains', 'orgUnits',
                       'chromeosdevices', 'mobiledevices', 'tokens',
                       'alerts', 'usageReports', 'messages', 'filters',
                       'delegates', 'forwardingAddresses', 'sendAs',
                       'resources']:
                if k in response:
                    items = response[k]
                    break

        if items:
            with open(outfile, 'a+', encoding='utf-8') as f:
                for item in items:
                    f.write(json.dumps(item) + '\n')
                f.flush()
                os.fsync(f)
            total_items += len(items)

        # Use list_next for pagination
        try:
            request = service.list_next(request_builder, response)
            request_builder = request  # Update for next iteration
        except AttributeError:
            request = None

    return total_items


class Lock:
    def __init__(self, fh):
        self.fh = fh

    def acquire(self):
        if self.fh != None:
            try:
                if sys.platform == 'win32':
                    msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    print("Acquired lock")
            except (IOError, BlockingIOError, PermissionError) as e:
                raise

    def release(self):
        if self.fh != None:
            try:
                if sys.platform == 'win32':
                    msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self.fh, fcntl.LOCK_UN)
                    print("released lock")
            except (IOError, BlockingIOError, PermissionError) as e:
                raise

    def __del__(self):
        if self.fh != None:
            self.fh.close()

def get_end_time_yesterday():
    yesterday = date.today() - timedelta(days=1)
    return datetime.combine(yesterday, datetime.max.time())

def get_date_range(config, logger=logging):
    """
    Description:
        Read in the date_start and date_end from the config

    Arguments:
        config: ConfigParser Object containing the goose config

    Returns:
        Tuple of (date_range_boolean, date_start, date_end)
    """
    date_range = False
    date_start = False
    date_end = False

    filters = config_get(config, 'filters', 'date_start', logger=logger)
    if  filters!= '' and filters is not None:
        date_range=True
        date_start = config_get(config, 'filters', 'date_start')
        if config_get(config, 'filters', 'date_end') != '':
            date_end = config_get(config, 'filters', 'date_end')
        else:
            date_end = datetime.now().strftime("%Y-%m-%d") +':00:00.000Z'
    else:
        date_range=False

    return (date_range, date_start, date_end)

def insert_time(time_range, start, end):
    if time_range == None:
        time_range = []
    record = {"start": start, "end": end}
    time_range.append(record)
    time_range = sorted(time_range, key=lambda x: x['start'])
    time_range = iter(time_range)
    new_time_range = []
    merged = next(time_range).copy()
    for entry in time_range:
        start, end = entry['start'], entry['end']
        if start <= merged['end']:
            # overlapping, merge
            merged['end'] = max(merged['end'], end)
        else:
            # distinct; yield merged and start a new copy
            new_time_range.append(merged)
            merged = entry.copy()
    new_time_range.append(merged)
    return new_time_range

def load_state(filepath, is_datetime=True, time_range=False, time_bounds=False):
    if os.path.isfile(filepath):
        end = open(filepath, "r").read()
        if is_datetime:
            end = dateutil.parser.parse(end)
        elif time_range or time_bounds:
            saved_time_range = json.loads(end)
            new_time_range = []
            for entry in saved_time_range:
                start, end = entry["start"], entry["end"]
                entry["start"] = dateutil.parser.parse(start)
                entry["end"] = dateutil.parser.parse(end)
                new_time_range.append(entry)
            return new_time_range
        return end

    return None

def save_state(filepath, end, start=None, is_datetime=True, time_range=False, time_bounds=False):
    if not filepath:
        return
    if is_datetime:
        cur_end = load_state(filepath)
        if cur_end and cur_end > end:
            end = cur_end
    elif time_range and start and end:
        cur_range = load_state(filepath, is_datetime=False, time_range=True)
        cur_range = insert_time(cur_range, start, end)
        end = json.dumps(cur_range, default=str)
    elif time_bounds:
        end = json.dumps(end, default=str)

    open(filepath, "w").write(f"{end}")

def find_time_gaps(time_range, start, end):
    """
    Description:
        finds the time gaps in time_range within start and end

    Arguments:
        time_range: list of dictionary time periods. Each with a start and end
        start: start time
        end: end time

    Returns:
        time gaps list
    """
    if time_range == None or len(time_range) == 0:
        return [{"start": start, "end": end}]
    gaps = []

    # add beginning gap if it exists
    if start < time_range[0]["start"]:
        gaps.append({"start": start, "end": time_range[0]["start"]})

    # for now we will just add all the gaps in time_range and if some of those overlap
    # with the start end time range we're interested then we'll grab those
    idx = 0
    while idx < len(time_range) - 1:
        cur_end = time_range[idx]["end"]
        next_start = time_range[idx+1]["start"]
        gaps.append({"start": cur_end, "end": next_start})
        idx += 1

    # add end gap if it exists
    if end > time_range[-1]["end"]:
        gaps.append({"start": time_range[-1]["end"], "end": end})


    actual_gaps = []
    for record in gaps:
        if record["start"] < end or record["end"] > start:
            max_start = max(record["start"], start)
            min_end = min(record["end"], end)
            actual_gaps.append({"start": max_start, "end": min_end})

    return actual_gaps


def read_auth(filepath: str, logger=logging, encryption_pw=None):
    try:
        authString = None
        dir_path = os.path.dirname(os.path.realpath(filepath))
        encrypted_filepath = os.path.join(dir_path, filepath + '.aes')
        if os.path.isfile(encrypted_filepath):
            if encryption_pw is None:
                encryption_pw = getpass.getpass("Please type the password for file encryption: ")
            with open(encrypted_filepath, "rb") as fIn:
                outStream = io.BytesIO()
                pyAesCrypt.decryptStream(fIn, outStream, encryption_pw)
                outStream.seek(0)
                authString = outStream.getvalue().decode()
                logger.debug("Decrypted the " + filepath + " file!")
        else:
            if os.path.isfile(filepath):
                authString = open(filepath, "r").read()
    except Exception as e:
        logger.error(f"Could not read current authfile: {str(e)}")
        sys.exit(1)

    return authString

def write_auth(filepath: str, writestr, logger=logging, encryption_pw=None, insecure=False):
    try:
        if not insecure:
            dir_path = os.path.dirname(os.path.realpath(filepath))
            encrypted_filepath = os.path.join(dir_path, filepath + '.aes')
            with open(encrypted_filepath, "wb") as fOut:
                inStream = io.BytesIO(bytearray(writestr, "utf-8"))
                pyAesCrypt.encryptStream(inStream, fOut, encryption_pw)
                logger.debug("Encrypted the " + filepath + " file!")
                # Delete the unencrypted filepath if it exists
                if os.path.isfile(filepath):
                    os.remove(filepath)
        else:
            with open(filepath, 'w') as outfile:
                outfile.write(writestr)
    except Exception as e:
        logger.error(f"Error writing auth to file: {str(e)}")

def get_authfile(authfile=".auth", ugt_authfile=".ugt_auth", logger=logging, encryption_pw=None):
    """
    Description:
        Read in Authfile to a dictionary

    Arguments:
        authfile=".auth": Path to the authentication file that contains the user and app credentials
        ugt_authfile=".ugt_auth": Path to the authentication file that contains the session json from authentication
        logger=logging: Logger

    Returns:
        Tuple of (auth_un_pw, auth)
        auth_un_pw: loaded in dictionary of the authfile config
        auth: loaded in dictionary of the ugt_authfile config
    """
    auth = {}

    dir_path = os.path.dirname(os.path.realpath(ugt_authfile))
    encrypted_auth = os.path.join(dir_path, authfile + '.aes')
    encrypted_authfile = os.path.join(dir_path, ugt_authfile + '.aes')
    if not os.path.isfile(ugt_authfile) and not os.path.isfile(encrypted_authfile):
        logger.warning("{} auth file missing. Please auth first. Exiting.".format(ugt_authfile))
        sys.exit(1)

    if os.path.isfile(encrypted_auth) and encryption_pw == None:
        encryption_pw = getpass.getpass("Please type the password for file encryption: ")

    auth_config_str = read_auth(authfile, logger=logger, encryption_pw=encryption_pw)

    auth_un_pw = configparser.ConfigParser()
    auth_un_pw.read_string(auth_config_str)

    ugt_auth_str = read_auth(ugt_authfile, logger=logger, encryption_pw=encryption_pw)
    auth = json.loads(ugt_auth_str)

    return (auth_un_pw, auth)
