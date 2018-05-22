import requests
import sys
from time import sleep
from random import randint


PATREON_CATEGORIES = ['video', 'comics', 'podcasts', 'comedy', 'diy', 'music', 'graphic', 'games', 'science',
                      'theater', 'writing', 'animation', 'photography', 'education', 'all']


class ParteonProcessor(object):
    def __init__(self, entity, log, retry=3):
        self.log = log
        self.retry = retry
        self.entity = entity
        self.base_url = "https://www.patreon.com/"
        self.headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) '
                                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}

    def _make_request(self, url):
        retries = 0
        while retries <= self.retry:
            try:
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError as e:
                self.log.info("{}".format(e))
                sleep(30)
                break
            except Exception as e:
                self.log.info("{}: Failed to make Twitch request on try {}".format(e, retries))
                retries += 1
                if retries <= self.retry:
                    self.log.info("Trying again!")
                    continue
                else:
                    sys.exit("Max retries reached")

    def _get_users(self):
        self.info = []
        response = self._make_request(self.base_url + "api/explore/category/4?include=creator.null&"
                                                      "fields[user]=full_name%2Cimage_url"
                                                      "%2Curl&fields[campaign]=creation_name"
                                                      "%2Cpatron_count%2Cpledge_sum%2Cis_monthly%2Cearnings_visibility&"
                                                      "page[count]=500&json-api-version=1.0")
        creators_list = response["data"]
        for creator in creators_list:
            try:
                user_data = self._get_user_info(creator)
                self.info.append(user_data)
                sleep(randint(4, 10))
            except:
                self.log.info("Failed to fetch creator: {}".format(creator))
                continue
        self.entity.save(users=self.info)

    def _get_user_info(self, creator):
        user_data = dict()
        url = creator["relationships"]["creator"]["links"]["related"]
        user_id = creator["id"]
        user_data["patrons"] = creator["attributes"]["patron_count"]
        try:
            user_data["monthly_cents"] = creator["attributes"]["pledge_sum"]
        except KeyError:
            user_data["monthly_cents"] = None

        user_info = self._make_request(url)
        user_data["name"] = user_info["data"]["attributes"]["full_name"]

        user_data["featured_tags"] = self._get_featured_tags(user_id)

        self.log.info(user_data)
        return user_data

    def _get_featured_tags(self, user_id):
        tags = []
        response = self._make_request("{}api/campaigns/{}/post-tags?timezone=Europe%2FMinsk&"
                                      "json-api-version=1.0".format(self.base_url, user_id))
        for t in response["data"]:
            is_featured = t["attributes"]["is_featured"]
            if is_featured:
                tag = "{} {} posts".format(t["attributes"]["value"], t["attributes"]["cardinality"])
                tags.append(tag)
        return ",".join(tags)

    def fetch(self):
        self.log.info('Making request to Patreon for daily creators export')
        self._get_users()
        return self
