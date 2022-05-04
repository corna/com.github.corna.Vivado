#!/usr/bin/env python3

import argparse
import bs4
import collections
import csv
import getpass
import http.cookiejar
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

NOTIFICATIONS_URL = 'https://www.xilinx.com/direct/swhelp/notifications.xml'
AUTHENTICATOR_URL = 'https://www.xilinx.com/bin/public/webinstall/sso/authenticator'
DOWNLOAD_LINK_URL = 'https://xilinx.entitlenow.com/wi/v1/downloadlink'
DOWNLOAD_PAGE_URL = ('https://www.xilinx.com', '/support/download/index.html')

installer_info = collections.namedtuple("installer_info", ['version', 'platform', 'md5', 'size'])
download_info = collections.namedtuple("download_info", ['version', 'filename', 'platform'])


class UnknownKey(NameError):
    pass


def get_downloads_from_api() -> dict[str, installer_info]:
    with urllib.request.urlopen(NOTIFICATIONS_URL) as response:
        raw_xml = response.read()

    root = ET.fromstring(raw_xml)

    notifications = root.iter('notification')
    notifications_version = filter(lambda n: n.get('type') == 'NEW_SW_NOTIFICATION_E', notifications)
    files = [(notification.get('version'), file) for notification in notifications_version for file in notification.findall('fileToDownlaod')]

    return {file.get('refKey'): installer_info(version,
                                               file.find('platform').text,
                                               file.find('md5Checksum').text,
                                               file.get('size')) for version, file in files}


def get_downloads_from_website() -> dict[str, installer_info]:
    with urllib.request.urlopen("".join(DOWNLOAD_PAGE_URL)) as response:
        raw_html = response.read()

    html = bs4.BeautifulSoup(raw_html, "lxml")

    # Get all the subpages
    subpages_tags = html.find_all(href=re.compile(r"downloadNav\/vivado-design-tools\/([0-9]+-[0-9]+|archive)\."))
    subpages = (DOWNLOAD_PAGE_URL[0] + tag["href"] for tag in subpages_tags)

    download_links = {}
    for subpage in subpages:
        download_links.update(get_downloads_from_page(subpage))

    return download_links


def get_downloads_from_page(link: str) -> dict[str, installer_info]:
    with urllib.request.urlopen(link) as response:
        raw_html = response.read()

    html = bs4.BeautifulSoup(raw_html, "lxml")

    download_tags = html.select("[class='download-links']")

    version_match = re.compile(r"[0-9]+\.[0-9]+")
    md5_match = re.compile(r"[^A-Fa-f0-9]([A-Fa-f0-9]{32})[^A-Fa-f0-9]")
    size_match = re.compile(r"([0-9]+(\.[0-9]+)?) +Mi?B")

    downloads = {}

    for download_tag in download_tags:
        link_tag = download_tag.find(href=re.compile(r"(Lin64\.bin|Win64\.exe)$"))
        if link_tag:
            # Get the link
            link = link_tag["href"]

            # Get the version
            version_found = version_match.search(link_tag.string)
            version = version_found.group() if version_found else None

            # Get the key
            key = link.split('=')[-1][:-4]

            # Get the (approximate) size
            try:
                size = round(float(size_match.search(str(download_tag)).group(1)) * 1024 * 1024)
            except (IndexError, ValueError):
                size = None

            # Get the MD5
            try:
                md5 = md5_match.search(str(download_tag)).group(1).lower()
            except IndexError:
                md5 = None

            # Get the platform
            platform = "LIN64" if link.endswith("Lin64.bin") else "WIN64"

            downloads[key] = installer_info(version=version, platform=platform, md5=md5, size=size)

    return downloads


def get_downloads() -> dict[str, installer_info]:
    downloads = {}

    # Get the downloads from the website, ignoring errors
    fail_reason = None
    try:
        downloads.update(get_downloads_from_website())
        if len(downloads) == 0:
            fail_reason = "no downloads found"
    except urllib.error.HTTPError as e:
        fail_reason = f"{e.code}: {e.reason}"
    except urllib.error.URLError as e:
        fail_reason = e.reason

    if fail_reason:
        print(f"Failed to get downloads from the Xilinx website ({fail_reason})", file=sys.stderr)

    # Get the downloads from the API
    downloads.update(get_downloads_from_api())

    return downloads


def get_auth_token(username: str, password: str) -> str:
    def get_cookie(base_url, params, cookie):
        url = base_url + "?" + urllib.parse.urlencode(params)
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        opener.open(url, data=b'')
        return next(filter(lambda c: c.name == cookie, cj)).value

    try:
        sso_token = get_cookie(AUTHENTICATOR_URL, {'xilinxUserId': username, 'password': password, "encrypted": "false"}, "SSOToken")
        auth_token = get_cookie(AUTHENTICATOR_URL, {"SSOToken": sso_token}, "token")
    except urllib.error.HTTPError as e:
        if e.code in (401, 404):
            print("invalid credentials. Make sure the provided e-mail and/or password are valid.")
        elif e.code == 503:
            print("the user profile is not complete. Complete your <a href=\"https://www.xilinx.com/myprofile/edit-profile.html\">user profile</a> to proceed with the download.")
        else:
            print("unknown authentication error.")
        raise e

    return auth_token


def get_download_info(download_list: str, key: str) -> download_info:
    filename_extensions = {"LIN64": "bin", "WIN64": "exe"}

    # Parse the download list, looking for a key match
    with open(download_list, 'r') as f:
        file_list_reader = csv.reader(f, delimiter='\t')
        for row in file_list_reader:
            if row[1] == key:
                platform = row[3]
                version = row[0]
                filename = row[1] + "." + filename_extensions[platform]
                break

    try:
        # Try to return the requested download info. This will raise NameError if the specified key has not been found
        return download_info(version=version, filename=filename, platform=platform)
    except NameError:
        raise UnknownKey


def get_download_link(token: str, info: download_info) -> str:
    # Build the request content
    request_content = {
        "files": [info.filename],
        "metadata": {
            "add_ons": [],
            "devices": [],
            "edition": "",
            "install_type": "Install",
            "number_parallel": 4,
            "platform": info.platform,
            "product_version": info.version,
            "products": ""
        },
        "token": token
    }

    # Build the request
    request = urllib.request.Request(
        DOWNLOAD_LINK_URL,
        data=json.dumps(request_content).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )

    # Make the request
    with urllib.request.urlopen(request) as response:
        raw_json = response.read()

    # Extract the download link
    download_link = json.loads(raw_json)["downloads"]["urls"][0]["download_link"]
    return urllib.parse.unquote(download_link)


def download_file_with_progress(url: str, output_file: str, version: str) -> None:
    def print_progress(transferred_blocks, block_size, total_size):
        transferred_size = transferred_blocks * block_size
        percentage = min(99, int(transferred_size / total_size * 100))
        transferred_mib = transferred_size / (1024 * 1024)
        total_mib = total_size / (1024 * 1024)

        try:
            print(f"#Downloading Vivado {version} ({transferred_mib:.1f} MiB / {total_mib:.1f} MiB, {percentage} %)\n{percentage}", file=sys.stderr, flush=True)
        except BrokenPipeError:     # The user has cancelled the download, everything is fine
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
            sys.exit(0)

    urllib.request.urlretrieve(url, output_file, print_progress)


if __name__ == "__main__":

    def get_downloads_and_print(args) -> None:
        def downloads_to_tsv(downloads: dict[str, installer_info]) -> str:
            downloads_list = [(d.version, k, str(d.size), d.platform, d.md5) for k, d in downloads.items()]
            return "\n".join(["\t".join(download) for download in sorted(downloads_list, key=lambda el: el[0], reverse=True)])

        downloads = get_downloads()

        # Filter by platforms
        downloads = {k: v for k, v in downloads.items() if v.platform in args.platforms.split(',')}

        # Convert to TSV
        downloads_tsv = downloads_to_tsv(downloads)

        # Save or print the list
        if args.output_file:
            with open(args.output_file, 'w') as f:
                f.write(downloads_tsv)
        else:
            print(downloads_tsv)

    def download_file(args) -> None:
        # Get the download data immediately, to fail early if the key or the download list file do not exist
        user_download_info = get_download_info(args.download_list, args.key)

        # Get the password from the user
        password = getpass.getpass() if sys.stdin.isatty() else sys.stdin.readline().rstrip()

        # Login to get a token and retrieve the download URL
        token = get_auth_token(args.username, password)
        download_link = get_download_link(token, user_download_info)

        # Download the file or simply print the download link
        if args.output_file:
            download_file_with_progress(download_link, args.output_file, user_download_info[0])
        else:
            print(download_link)

    parser = argparse.ArgumentParser(description="Find and download the Xilinx Vivado Design Suite.")
    subparsers = parser.add_subparsers()

    list_parser = subparsers.add_parser('list', help="Get the list of downloadable versions")
    list_parser.add_argument("-p", "--platforms", type=str, help="Comma-separated list of the installer platforms", default="LIN64,WIN64")
    list_parser.add_argument("-o", "--output-file", type=str, help="Output filename where to save the download list")
    list_parser.set_defaults(func=get_downloads_and_print)

    download_parser = subparsers.add_parser('download', help="Download a specific file")
    download_parser.add_argument("download_list", type=str, help="Download list")
    download_parser.add_argument("key", type=str, help="The key of the file to download")
    download_parser.add_argument("username", type=str)
    download_parser.add_argument("-o", "--output-file", type=str, help="Save to file instead of printing the result on the stdout.")
    download_parser.set_defaults(func=download_file)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
