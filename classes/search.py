# -*- coding: utf-8 -*-
# #!/bin/env python

import requests
from bs4 import BeautifulSoup

import urllib.request, urllib.error, urllib.parse

import logging
import sys
import re
import os

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)-5s - %(message)s",
                    level=logging.INFO,
                    datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger(__name__)

try:
    import settings
    import event
    import start_date
    import person
except ImportError as exc:
    sys.exit(f"Failed to import module ({exc})")

# CONSTANTS AND CONVERTER DICTIONARIES, NO NEED TO AMEND THESE EXCEPT IF ADDING NEW EVENTS
# ----------------------------------------------------------------------------------------------------------------------
EXPECTED_DOMAIN = {"AO": "fsatresults", "Lombardia": "fisg", "USClassic": "usfigureskating", "Nepela": "kraso",
                   "ACI": "skatecanada", "Nebelhorn": "isuresults", "Finlandia": "figureskatingresults",
                   "Tallinn": "data.tallinntrophy", "Warsaw": "pfsa", "GoldenSpin": "netlify",
                   "DenkovaStaviksi": "clubdenkovastaviski", "IceStar": "figure.skating.by",
                   "MordovianOrnament": "fsrussia"}

DBNAME_TO_URLNAME = {"NHK": "gpjpn", "TDF": "gpfra", "SC": "gpcan", "COR": "gprus", "SA": "gpusa", "COC": "gpchn",
                     "GPF": "gpf", "WC": "wc", "4CC": "fc", "OWG": "owg", "WTT": "wtt", "EC": "ec", "AO": "ISUCSAO",
                     "Lombardia": "lombardia", "Nepela": "ont", "Finlandia": "CSFIN", "Nebelhorn": "nt",
                     "ACI": "CSCAN", "Warsaw": "warsawcup", "USClassic": "us_intl_classic",
                     "GoldenSpin": "", "DenkovaStaviksi": "ISUCS", "IceStar": "Ice_Star", "MordovianOrnament": "CSRUS"}

MAX_TRIES = 10  # before timeout on .get() requests


HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/68.0.3440.106 Safari/537.36"}

ROOT_DOMAIN_PATTERN = re.compile(r"^((?:http(?:s)?://)?(www)?[A-Za-z\d\-]{3,}\.[a-z.]{2,6})(?:/)")

JUDGE_PAGE_TITLE = re.compile(r"(Team)?(Junior)? (Men|Ladies|Ice Dance|Pairs)( Single Skating)? - (Short|Rhythm|Free) "
                              r"(Program|Dance)")

SEARCHTERM_TO_DBNAME = {"nhk+trophy": "NHK", "rostelecom+cup": "COR", "france": "TDF", "canada": "SC", "russia": "COR",
                        "skate+america": "SA", "cup+of+china": "COC", "grand+prix+final": "GPF",
                        "world+figure+skating+championships": "WC", "four+continents+championship": "4CC",
                        "olympic+winter+games": "OWG", "world+team+trophy": "WTT",
                        "european+figure+skating+championships": "EC",
                        "trophee+eric+bompard": "TDF", "asian+open": "AO", "lombardia+trophy": "Lombardia",
                        "us+figure+skating+classic": "USClassic", "ondrej+nepela+trophy": "Nepela",
                        "autumn+classic+international": "ACI", "nebelhorn+trophy": "Nebelhorn",
                        "finlandia+trophy": "Finlandia", "tallinn+trophy": "Tallinn", "warsaw+cup": "Warsaw",
                        "golden+spin+zagreb": "GoldenSpin", "denkova+staviski+cup": "DenkovaStaviksi",
                        "ice+challenge": "IceChallenge", "ice+star": "IceStar", "volvo+open+cup": "Volvo",
                        "mordovian+ornament": "MordovianOrnament"}

# ----------------------------------------------------------------------------------------------------------------------


class EventSearch:
    def __init__(self, category, per_disc_settings, search_year, search_phrase, url=None):
        self.search_string = search_phrase

        event_name = SEARCHTERM_TO_DBNAME[search_phrase]
        self.event = event.Event(name=event_name, year=search_year)

        self.category = category
        self.per_disc_settings = per_disc_settings

        self.expected_domain = EXPECTED_DOMAIN[self.event.name] if self.event.name in EXPECTED_DOMAIN else None
        self.fed_abbrev = DBNAME_TO_URLNAME[self.event.name] if self.event.name in DBNAME_TO_URLNAME else None

        self.homepage_url = url
        self.homepage, self.homepage_text = _get_page_content(self.homepage_url)

    def _test_result(self, url):
        """Checks that a google search hit satisfies the condition that make it a likely event homepage
        (e.g. that it occurs in the expected year, was posted on the expected domain, etc.)
        """
        if " " in url:
            return False, None, None

        isuresults_test = (self.event.is_A_comp and "isuresults" in url)
        if self.expected_domain:
            other_expected_domain_test = (not self.event.is_A_comp and self.expected_domain in url)
        else:
            other_expected_domain_test = False
        domain_test = isuresults_test or other_expected_domain_test

        logger.debug(f"Testing {url} -- domain test: {domain_test}")

        if self.fed_abbrev:
            gpf_pattern = (self.fed_abbrev == "gpf") and (
                        str(self.event.year)[-2:] + str(self.event.year + 1)[-2:] in url)
            name_test = self.fed_abbrev in url
            logger.debug(f"Testing {url} -- name test: {name_test}")
        else:
            gpf_pattern, name_test = False, False

        season_pattern = str(self.event.year) in url or \
                         (self.event.season[2:] in url and str(int(self.event.season[2:]) + 1) in url) or \
                         self.event.season[4:] + str(int(self.event.season[4:]) + 1) in url

        filters = all(domain not in url for domain in ["goldenskate", "wiki", "bios", "revolvy"])
        url_test = [domain_test, (gpf_pattern or season_pattern), name_test]
        logger.debug(
            f"domain test {domain_test}, gpf pattern {gpf_pattern}, season_pattern {season_pattern}, name test {name_test}")

        r = request_url("http://" + url if "http" not in url else url)
        event_page = BeautifulSoup(r.content, "html5lib")
        raw_text = " ".join([s for s in event_page.strings])
        compact_text = "".join([i for i in raw_text if i != "\t" and i != "\n"])
        required_strings = self.event.search_string.split("+") + [str(self.event.year)]
        text_test = all(i.lower() in compact_text.lower() for i in required_strings)

        logger.debug(f"sum url test {sum(url_test)} text test {text_test}")
        if filters and (sum(url_test) >= 3 or text_test):
            logger.info(
                f"URL {url} passed tests for {self.event.name} {self.event.year} with {sum(url_test)}, {text_test}.")
            return True, event_page, compact_text
        else:
            logger.info(f"URL {url} failed tests for {self.event.name} {self.event.year}.")
            return False, None, None

    def _construct_absolute_url(self, sublink):
        """Combines a url and a relative link found on the url's page and returns one absolute url.

        Two cases: (1) If sublink is relative to a subdomain (e.g. "xx.pdf"), strips "index" portion of the the
        subdomain url and appends sublink to it (e.g. "pokemon.io/woot/index.html" becomes "pokemon.io/woot/").
        (2) If sublink has an address that is relative to the root domain (e.g. "/wahey/yeah/xx.pdf"), extract root
        domain only ("pokemon.io") from subdomain url and append to that sub_link -- A relative link found on the event
        homepage
        """
        if sublink[:4] == "http":
            root = ""
        elif sublink[0] == "/":
            root = re.search(ROOT_DOMAIN_PATTERN, self.homepage_url).group(1)
        elif "index" in self.homepage_url:
            root = re.sub(r"/index[A-Za-z\d]*\.htm[l]*$", "/", self.homepage_url)
        else:
            root = self.homepage_url
        temp = root + sublink
        return "http://" + temp if temp[:4] != "http" else temp

    def set_event_homepage(self):
        """Performs google search for results from a given event & year, returns first result that passes tests/
        """
        domain = "isu" if self.event.is_A_comp else ""
        search = "https://www.google.co.uk/search?q=" + domain + "+results+" + self.event.search_string \
                 + "+" + str(self.event.year)  # + self.category
        logger.info(f"Running google search {search}")

        google_r = request_url(url=search, on_failure=None)
        google_page = BeautifulSoup(google_r.text, "html.parser")

        for l in google_page.find_all("cite"):
            test, homepage, homepage_text = self._test_result(url=l.text)
            if test:
                self.homepage_url = l.text
                self.homepage = homepage
                self.homepage_text = homepage_text
                self.set_start_date()
                break
        if not self.homepage_url:
            return False
        else:
            return True

    def set_start_date(self):
        """Scrapes an event page and returns its start date in datetime (extracted from a "start date - end date" range)
        """
        try:
            self.event.start_date = start_date.EventDate(year=self.event.year, h2_event_flag=self.event.is_h2_event,
                                                   text_to_parse=self.homepage_text)
        except ValueError as verr:
            sys.exit(f"Could not parse date from text for {self.event.name} {self.event.year}: {verr}")

    def generate_pdf_filename(self, pdf_link, disc_code):
        """Generates the pdf filename from the sublink and other known event identifiers
        """
        raw_name = pdf_link.rpartition("/")[2]
        if re.search(r"data[0-9]{4}", raw_name):
            length = "S" if disc_code[2:] == "03" else "F"
            programme_type = "D" if event.DISC_CODES_DIC[disc_code] == "Dance" else "P"
            filename = "_".join([self.event.name + str(self.event.year), event.DISC_CODES_DIC[disc_code],
                                 length + programme_type]) + ".pdf"
        else:
            filename = self.event.name + "_" + raw_name
        return self.event.start_date.start_date.strftime("%y%m%d") + "_" + filename

    def download_pdf_protocols(self):
        """Downloads the pdf scoring protocols for the requested disciplines from the event page.

        Keyword arguments:
        event_page -- BeautifulSoup parsed requests object
        event_start_date -- datetime object denoting the start of the event, used in pdf filename
        per_discipline_settings -- Dictionary of bools structured as follows {"men": True, "ladies": True, "pairs":
        True, "dance": True}
        """
        all_sublinks = list(set([a.get("href") for a in self.homepage.find_all("a")]))
        for sublink in all_sublinks:
            logger.debug(f"Examining {sublink} for {self.event.name} {self.event.year}")

            # Loop through each discipline, checking the setting in settings dic and loading the correct dic of codes
            for disc in self.per_disc_settings:
                if self.per_disc_settings[disc]:

                    for code in event.DISC_CODES_DICS[disc.upper() + "_CODES"]:
                        if re.search(code, str(sublink)) and "novice" not in str(sublink).lower():
                            logger.info(f"Code {code} matches {sublink}")

                            filename = self.generate_pdf_filename(pdf_link=sublink, disc_code=code)
                            full_url = self._construct_absolute_url(sublink=sublink)

                            # Get contents of sublink
                            try:
                                req = urllib.request.Request(full_url, headers=HEADERS)
                                res = urllib.request.urlopen(req)
                            except urllib.error.HTTPError as herr:
                                logger.error(f"HTTP {str(herr.code)} error opening {full_url}")
                            except urllib.error.URLError as uerr:
                                logger.error(f"URL error opening {full_url}: {uerr.reason}")
                            else:
                                pdf = open(settings.WRITE_PATH + filename, "wb")
                                pdf.write(res.read())
                                pdf.close()

    def scrape_judging_panel(self, event, last_row_dic, panel_list, judge_list):

        all_sublinks = list(set([a.get("href") for a in self.homepage.find_all("a")]))
        for sublink in all_sublinks:
            logger.debug(f"Examining {sublink} for {self.event.name} {self.event.year}")

            if sublink and sublink.lower().endswith(".htm") and not sublink.lower().endswith("index.htm"):
                full_url = self._construct_absolute_url(sublink=sublink)
                page, text = _get_page_content(full_url)

                title_search = re.search(JUDGE_PAGE_TITLE, text)
                if title_search and "Panel of" in text:
                    logger.debug(f"Found required elements in page {title_search.group(0)}")

                    # --- Set segment, sub_event, discipline and category
                    segment = title_search.group(5)[0] + title_search.group(6)[0]
                    discipline = "IceDance" if title_search.group(3) == "Ice Dance" else title_search.group(5)
                    category = "Jr" if title_search.group(2) == "Junior" else "Sr"
                    sub_event = title_search.group(1)

                    # --- Extract and clean panel data
                    roles_table = [re.sub(r"\n+", "", td.get_text()).strip() for td in page.find_all('td')]
                    logger.debug(f"Roles table is {roles_table}")

                    segment_judges = []

                    # Find increment (sometimes country appears twice)
                    indices = [roles_table.index(r) for r in
                               ["Referee", "Technical Controller", "Technical Controller"]]
                    first_entry = min(indices)
                    increment = 4 if (roles_table[first_entry + 2] == roles_table[first_entry + 3]) else 3
                    last = 16 * increment

                    for i in range(first_entry, last, increment):
                        # Align 'judge' notation with the one used in scoring tables
                        if 'Judge' in roles_table[i] or 'No.' in roles_table[i]:
                            role = "J" + str(roles_table[i][-1]).zfill(2)
                        else:
                            role = roles_table[i]

                        official = person.Official(name_string=roles_table[i+1], fed=roles_table[i+2],
                                                   last_row_dic=last_row_dic, judge_list=judge_list)

                        # Construct and append tuple
                        segment_judges.append((season, year, event, sub_event, discipline, category, segment,
                                               role, name, raw_roles[i + 2]))
                    except IndexError:
                        sys.exit(f"Fewer officials than expected in {self.event.name} {self.event.year} "
                                 f"{discipline} {category} {segment}")

                    print('segment judges: ', segment_judges)
                    event_judges.extend(segment_judges)

            all_judges.extend(event_judges)

            labels = ['season', 'year', 'event', 'sub_event', 'discipline', 'category', 'segment', 'role', 'name',
                      'country']

            df = pd.DataFrame.from_records(all_judges, columns=labels)

            # def get_country(row):
            #     if row['country'] != 'ISU':
            #         return row['country']
            #     else:
            #         res = df.loc[(df['country'] != 'ISU') & (df['name'] == row['name'])] \
            #             .assign(year_diff=(df['year']-row['year']).abs())
            #         return res.loc[res['year_diff'].idxmin(), 'country'] if not res.empty else 'ISU'
            #
            # df['country'] = df.apply(get_country, axis=1)
            #
            # print(df)

            path = os.path.expanduser('~/Desktop/bias/output/')
            df.to_csv(path + 'judges_1617to1718.csv', mode='a', header=True)


def request_url(url, on_failure=None, *args):
    """Requests provided url up to MAX_TRIES times, and implements error handler function if provided.

    Requests provided url up to MAX_TRIES times, and implements error handler function if provided - e.g. to fetch
    second page of google results in case of not correct match on first page. No default error handler function provided.
    Keyword arguments:
    url -- url to request
    on_failure -- function to handle any HTTP or
    terms_to_search -- list of competition names
    """
    r = None
    for i in range(0, MAX_TRIES):
        try:
            r = requests.get(url, headers=HEADERS, timeout=3)
            r.raise_for_status()
        except requests.exceptions.Timeout as terr:
            logger.error(f"Timeout error on {url} on try {i+1}: {terr}")
            continue
        except requests.exceptions.HTTPError as herr:
            if on_failure:
                logger.error(f"HTTP error on {url}, implementing alternative: {herr}")
                on_failure(*args)
                break
            else:
                logger.error(f"HTTP error on {url}, no do overs: {herr}")
                sys.exit(1)
        except requests.exceptions.TooManyRedirects as rerr:
            if on_failure:
                logger.error(f"HTTP error on {url}, implementing alternative: {rerr}")
                on_failure(*args)
                break
            else:
                logger.error(f"HTTP error on {url}, no do overs: {rerr}")
                sys.exit(1)
        except requests.exceptions.RequestException as err:
            logger.error(f"Failed on {url}: {err}")
            sys.exit(1)
        break
    return r


def _get_page_content(url=None):
    if url:
        r = request_url("http://" + url if "http" not in url else url)
        page = BeautifulSoup(r.content, "html5lib")
        raw_text = " ".join([s for s in page.strings])
        compact_text = "".join([i for i in raw_text if i != "\t" and i != "\n"])
        return page, compact_text
    else:
        return None, None


def remove_newlines(str):
    return str.replace('\r', '').replace('\n', '')


if __name__ == "__main__":
    # Woot tests

