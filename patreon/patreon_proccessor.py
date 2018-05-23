import requests
import sys
from time import sleep
from random import randint
from datetime import datetime


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
        self.relations = []
        response = self._make_request(self.base_url + "api/explore/category/99?include=creator.null&"
                                                      "fields[user]=full_name%2Cimage_url"
                                                      "%2Curl&fields[campaign]=creation_name"
                                                      "%2Cpatron_count%2Cpledge_sum%2Cis_monthly%2Cearnings_visibility&"
                                                      "page[count]=50&json-api-version=1.0")
        creators_list = response["data"]
        for creator in creators_list:
            try:
                user_data, relations = self._get_user_info(creator)
                self.info.append(user_data)
                for relation in relations:
                    self.relations.append(relation)
                sleep(randint(4, 10))
            except Exception as e:
                self.log.info("Failed to fetch creator: {}".format(e))
                continue
        self.entity.save(users=self.info, relations=self.relations)

    def _get_user_info(self, creator):
        user_data = dict()
        url = creator["relationships"]["creator"]["links"]["related"]
        relation_id = creator["relationships"]["creator"]["data"]["id"]
        user_id = creator["id"]
        uri = "patreon␟user␟{}".format(user_id)
        user_data["uri"] = uri
        user_data["followers"] = creator["attributes"]["patron_count"]
        description = creator["attributes"]["creation_name"]
        user_data["profile"] = "creating {}".format(description)
        user_data["date"] = datetime.now().date()
        try:
            user_data["platform_income"] = creator["attributes"]["pledge_sum"]
        except KeyError:
            user_data["platform_income"] = None

        user_info = self._make_request(url)
        screen_name = user_info["data"]["attributes"]["vanity"]
        full_name = user_info["data"]["attributes"]["full_name"]
        user_data["screen_name"] = screen_name if screen_name else full_name
        user_data["full_name"] = full_name
        user_data["ingested"] = False
        user_data["url"] = user_info["data"]["attributes"]["url"]
        user_data["categories"] = self._get_featured_tags(user_id)
        user_data["post_count"] = self._get_post_count(relation_id)

        user_relations = self._get_user_relations(user_info, uri)

        self.log.info(user_data)
        self.log.info(user_relations)
        return user_data, user_relations

    def _get_featured_tags(self, user_id):
        tags = []
        response = self._make_request("{}api/campaigns/{}/post-tags?timezone=UTC&"
                                      "json-api-version=1.0".format(self.base_url, user_id))
        for t in response["data"]:
            is_featured = t["attributes"]["is_featured"]
            if is_featured:
                tag = "{} {} posts".format(t["attributes"]["value"], t["attributes"]["cardinality"])
                tags.append(tag)
        return tags

    def _get_post_count(self, relation_id):
        response = self._make_request("{}api/stream?page[cursor]=null&filter[is_by_creator]=true"
                                      "&filter[is_following]=false&filter[creator_id]={}"
                                      "&filter[contains_exclusive_posts]=true&include=recent_comments.commenter"
                                      "%2Crecent_comments.commenter.flairs.campaign.creator%2Crecent_comments.parent"
                                      "%2Crecent_comments.post%2Crecent_comments.first_reply.commenter"
                                      "%2Crecent_comments.first_reply.parent%2Crecent_comments.first_reply.post"
                                      "&fields[comment]=body%2Ccreated%2Cdeleted_at%2Cis_by_patron"
                                      "%2Cis_by_creator%2Cvote_sum%2Ccurrent_user_vote%2Creply_count"
                                      "&fields[post]=comment_count&fields[user]=image_url%2Cfull_name%2Curl"
                                      "&fields[flair]=image_tiny_url%2Cname&json-api-use-default-includes=false"
                                      "&json-api-version=1.0".format(self.base_url, relation_id))
        try:
            count = response["meta"]["posts_count"]
        except KeyError:
            count = 0
        return count

    def _get_user_relations(self, user_data, src_uri):
        relations = list()
        facebook_relation = dict()
        twitch_relation = dict()
        twitter_relation = dict()
        youtube_relation = dict()

        facebook_url = user_data["data"]["attributes"]["facebook"]
        twitch_url = user_data["data"]["attributes"]["twitch"]
        twitter_url = user_data["data"]["attributes"]["twitter"]
        youtube_url = user_data["data"]["attributes"]["youtube"]

        if facebook_url:
            screen_name = self._get_url_screen_name(facebook_url)
            facebook_relation["src"] = src_uri
            facebook_relation["relation"] = 4
            facebook_relation["ingested"] = False
            facebook_relation["dst"] = "facebook␟page␟{}".format(screen_name)
            relations.append(facebook_relation)

        if twitch_url:
            twitch_relation["src"] = src_uri
            twitch_relation["relation"] = 100
            twitch_relation["ingested"] = False
            twitch_relation["dst"] = "twitch␟screen_name␟{}".format(self._get_url_screen_name(twitch_url))
            relations.append(twitch_relation)

        if twitter_url:
            name = self._get_url_screen_name(twitter_url)
            uri = "twitter␟{}␟{}".format("user" if name.isdigit() else "screen_name", name)
            twitter_relation["src"] = src_uri
            twitter_relation["relation"] = 100
            twitter_relation["ingested"] = False
            twitter_relation["dst"] = uri
            relations.append(twitter_relation)

        if youtube_url:
            name = self._get_url_screen_name(youtube_url)
            uri = "youtube␟{}␟{}".format("channel" if "channel" in youtube_url else "user", name)
            youtube_relation["src"] = src_uri
            youtube_relation["relation"] = 100
            youtube_relation["ingested"] = False
            youtube_relation["dst"] = uri
            relations.append(youtube_relation)

        return relations

    def _get_url_screen_name(self, url):
        url = url.replace("/", " ")
        url = url.replace("?ref=ts", " ")
        url = url.replace("?ref=hl", " ")
        url = url.replace("?view_as=subscriber", " ")
        url = url.rstrip()
        return url.split(" ")[-1]

    def fetch(self):
        self.log.info('Making request to Patreon for daily creators export')
        self._get_users()
        return self
