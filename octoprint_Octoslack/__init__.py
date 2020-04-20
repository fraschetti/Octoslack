# coding=utf-8
# encoding: utf-8
from __future__ import absolute_import, division, print_function, unicode_literals
from octoprint.util.version import get_octoprint_version_string
from tempfile import mkstemp
from datetime import timedelta
from slacker import Slacker, IncomingWebhook
from imgurpython import ImgurClient
from imgurpython.helpers.error import ImgurClientError, ImgurClientRateLimitError
from pushbullet import Pushbullet
from pushover_complete import PushoverAPI
from rocketchat.api import RocketChatAPI
from matrix_client.client import MatrixClient
from matrix_client.client import Room as MatrixRoom
from PIL import Image
from octoprint.util import RepeatedTimer
from websocket import WebSocketConnectionClosedException
from minio import Minio
from sarge import run, Capture, shell_quote
from discord_webhook import DiscordWebhook, DiscordEmbed
import octoprint.util
import octoprint.plugin
import six.moves.urllib.request, six.moves.urllib.error, six.moves.urllib.parse
import datetime
import base64
import six.moves.queue
import json
import os
import os.path
import uuid
import time
import datetime
import tinys3
import humanize
import time
import threading
import requests
import math
import re
import copy
import netifaces
import pytz
import socket
import pymsteams
from six import unichr
from six.moves import zip

try:
    # Python2
    from slackclient import SlackClient
except ImportError:
    # Python3
    import slack
    import asyncio

SLACKER_TIMEOUT = 60
COMMAND_EXECUTION_WAIT = 10


class OctoslackPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ShutdownPlugin,
    octoprint.plugin.ProgressPlugin,
    octoprint.plugin.EventHandlerPlugin,
    octoprint.plugin.TemplatePlugin,
):

    ##TODO FEATURE - generate an animated gif of the print - easy enough if we can find a python ib to create the gif (images2gif is buggy & moviepy, imageio, and and visvis which rely on numpy haven't worked out as I never neven let numpy try to finish installing after 5/10 minutes on my RasPi3)
    ##TODO FEATURE - add the timelapse gallery for cancelled/failed/completed as a single image
    ##TODO FEATURE - Add support for Imgur image title + description
    ##TODO FEATURE - Optionally upload timelapse video to youtube & send a Slack message when the upload is complete
    ##TODO FEATURE - Define a third set of messages for each event to allow sending M117 commands to the printer
    ##TODO ENHANCEMENT - The progress event fires on gcode uploads and triggers Octoslack events. Test and fix if necessary.
    ##TODO ENHANCEMENT - Consider extending the progress snapshot minimum interval beyond Slack to other providers
    ##TODO ENHANCEMENT - Add Persoanl Token, emoji, avatar, and other formatting enhancements to Rocket.API once a library supports them (or update the libs yourself)
    ##TODO We've certainly moved past "it's time to refactor" line. Both the UI/JS/Python code need to be refactored
    ##TODO add multi-cam support: https://plugins.octoprint.org/plugins/multicam/

    ##~~ SettingsPlugin mixin

    def get_settings_defaults(self):
        return {
            "connection_method": "APITOKEN",
            "slack_apitoken_config": {
                "api_token": "",
                "enable_commands": True,
                "commands_positive_reaction": ":thumbsup:",
                "commands_negative_reaction": ":thumbsdown:",
                "commands_processing_reaction": ":stopwatch:",
                "commands_unauthorized_reaction": ":lock:",
            },
            "slack_webhook_config": {"webhook_url": ""},
            "slack_identity": {
                "existing_user": True,
                "icon_url": "",
                "icon_emoji": "",
                "username": "",
            },
            "slack_rtm_enabled_commands": {
                "help": {"enabled": True, "restricted": False},
                "status": {"enabled": True, "restricted": False},
                "stop": {"enabled": True, "restricted": False},
                "pause": {"enabled": True, "restricted": False},
                "resume": {"enabled": True, "restricted": False},
            },
            "slack_rtm_authorized_users": "",
            "channel": "",
            "pushbullet_config": {"access_token": "", "channel": ""},
            "pushover_config": {"app_token": "", "user_key": ""},
            "rocketchat_config": {
                "server_url": "",
                "username": "",
                "password": "",
                "channel": "",
            },
            "matrix_config": {
                "server_url": "",
                "access_token": "",
                "user_id": "",
                "channel": "",
            },
            "discord_config": {
                "webhook_urls": "",
                "alternate_username": "",
                "avatar_url": "",
            },
            "teams_config": {"webhook_urls": ""},
            "ignore_cancel_fail_event": True,
            "mattermost_compatability_mode": False,
            "include_raspi_temp": True,
            "snapshot_upload_method": "NONE",
            "imgur_config": {
                "client_id": "",
                "client_secret": "",
                "refresh_token": "",
                "album_id": "",
            },
            "s3_config": {
                "AWSAccessKey": "",
                "AWSsecretKey": "",
                "s3Bucket": "",
                "file_expire_days": -1,
                "URLStyle": "PATH",
            },
            "minio_config": {
                "AccessKey": "",
                "SecretKey": "",
                "Bucket": "",
                "Endpoint": "s3.amazonaws.com",
                "secure": True,
            },
            "additional_snapshot_urls": "",
            "snapshot_arrangement": "HORIZONTAL",  ##HORIZTONAL or VERTICAL or GRID
            "time_format": "HUMAN",  ##FUZZY or EXACT or HUMAN
            "supported_events": {
                ##Not a real event but we'll leverage the same config structure
                "Help": {
                    "Enabled": True,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign: Help - Supported commands :question:",
                    "Fallback": "",
                    "Color": "good",
                    "CaptureSnapshot": False,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": False,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportFinalPrintTime": False,
                    "ReportMovieStatus": False,
                    "IncludeSupportedCommands": True,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "Startup": {
                    "Enabled": False,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Octoprint service started :chart_with_upwards_trend:",
                    "Fallback": "Octoprint service started",
                    "Color": "good",
                    "CaptureSnapshot": False,
                    "ReportPrinterState": True,
                    "ReportEnvironment": True,
                    "ReportJobState": False,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportFinalPrintTime": False,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "Shutdown": {
                    "Enabled": False,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Octoprint service stopped :chart_with_downwards_trend:",
                    "Fallback": "Octoprint service stopped",
                    "Color": "good",
                    "CaptureSnapshot": False,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": False,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportFinalPrintTime": False,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "Connecting": {
                    "Enabled": False,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Connecting to printer :satellite:",
                    "Fallback": "Connecting to printer",
                    "Color": "good",
                    "CaptureSnapshot": False,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": False,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportFinalPrintTime": False,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "Connected": {
                    "Enabled": False,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Successfully connected to printer :computer:",
                    "Fallback": "Successfully connected to printer",
                    "Color": "good",
                    "CaptureSnapshot": False,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": False,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportFinalPrintTime": False,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "Disconnecting": {
                    "Enabled": False,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Printer disconnecting :confused:",
                    "Fallback": "Printer disconnecting",
                    "Color": "warning",
                    "CaptureSnapshot": False,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": False,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportFinalPrintTime": False,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "Disconnected": {
                    "Enabled": False,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Printer disconnected :worried:",
                    "Fallback": "Printer disconnected",
                    "Color": "danger",
                    "CaptureSnapshot": False,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": False,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportFinalPrintTime": False,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "Error": {
                    "Enabled": True,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Printer error :fire:",
                    "Fallback": "Printer error: {error}",
                    "Color": "danger",
                    "CaptureSnapshot": True,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": False,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportFinalPrintTime": False,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "PrintStarted": {
                    "Enabled": True,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  A new print has started :rocket:",
                    "Fallback": "Print started: {print_name}, Estimate: {remaining_time}",
                    "Color": "good",
                    "CaptureSnapshot": True,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": True,
                    "ReportJobOrigEstimate": True,
                    "ReportJobProgress": False,
                    "ReportFinalPrintTime": False,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "PrintFailed": {
                    "Enabled": True,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Print failed :bomb:",
                    "Fallback": "Print failed: {print_name}",
                    "Color": "danger",
                    "CaptureSnapshot": True,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": True,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportFinalPrintTime": False,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "PrintCancelling": {
                    "Enabled": True,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Print is being cancelled :no_good:",
                    "Fallback": "Print is being cancelled: {print_name}",
                    "Color": "warning",
                    "CaptureSnapshot": True,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": True,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": True,
                    "ReportFinalPrintTime": False,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "PrintCancelled": {
                    "Enabled": True,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Print cancelled :no_good:",
                    "Fallback": "Print cancelled: {print_name}",
                    "Color": "warning",
                    "CaptureSnapshot": True,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": True,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportFinalPrintTime": False,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "PrintDone": {
                    "Enabled": True,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Print finished successfully :dancer:",
                    "Fallback": "Print finished successfully: {print_name}, Time: {elapsed_time}",
                    "Color": "good",
                    "CaptureSnapshot": True,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": True,
                    "ReportJobOrigEstimate": True,
                    "ReportJobProgress": False,
                    "ReportFinalPrintTime": True,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                ##Not a real event but we'll leverage the same config structure
                "Progress": {
                    "Enabled": False,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign: Print progress {pct_complete} :horse_racing:",
                    "Fallback": "Print progress: {pct_complete} - {print_name}, Elapsed: {elapsed_time}, Remaining: {remaining_time}",
                    "Color": "good",
                    "CaptureSnapshot": True,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": True,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": True,
                    "ReportMovieStatus": False,
                    "UpdateMethod": "NEW_MESSAGE",
                    # Minimum time in minutes to wait before uploading a snapshot again for a progress upload
                    "SlackMinSnapshotUpdateInterval": 10,
                    "IntervalPct": 25,
                    "IntervalHeight": 0,
                    "IntervalTime": 0,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                ##Not a real event but we'll leverage the same config structure
                "GcodeEvent": {
                    "Enabled": False,  ##Overwritten by each event
                    "ChannelOverride": "",  ##Overwritten by each event
                    "Message": "",  ##Overwritten by each event
                    "Fallback": "",  ##Overwritten by each event
                    "Color": "good",  ##Hardcoded to 'good' for now
                    "CaptureSnapshot": False,  ##Overwritten by each event
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": True,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": True,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                ##Not a real event but we'll leverage the same config structure
                "Heartbeat": {
                    "Enabled": False,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign: Heartbeat - Printer status: {printer_status} :heartbeat:",
                    "Fallback": "Heartbeat - Printer status: {printer_status}",
                    "Color": "good",  ##Color may be updated in process_slack_event
                    "CaptureSnapshot": False,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": False,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportMovieStatus": False,
                    "IntervalTime": 60,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "PrintPaused": {
                    "Enabled": True,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Print paused :zzz:",
                    "Fallback": "Print paused: {pct_complete} - {print_name}",
                    "Color": "warning",
                    "CaptureSnapshot": True,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": True,
                    "ReportJobOrigEstimate": True,
                    "ReportJobProgress": True,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "PrintResumed": {
                    "Enabled": True,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Print resumed :runner:",
                    "Fallback": "Print resumed: {pct_complete} - {print_name}",
                    "Color": "good",
                    "CaptureSnapshot": True,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": True,
                    "ReportJobOrigEstimate": True,
                    "ReportJobProgress": True,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "MetadataAnalysisStarted": {
                    "Enabled": False,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  File analysis started :runner:",
                    "Fallback": "File metadata analysis started: {print_name}",
                    "Color": "good",
                    "CaptureSnapshot": False,
                    "ReportPrinterState": False,
                    "ReportEnvironment": False,
                    "ReportJobState": False,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "MetadataAnalysisFinished": {
                    "Enabled": False,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  File analysis complete :ok_hand:",
                    "Fallback": "File metadata analysis complete: {print_name}",
                    "Color": "good",
                    "CaptureSnapshot": False,
                    "ReportPrinterState": False,
                    "ReportEnvironment": False,
                    "ReportJobState": False,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportMovieStatus": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "MovieRendering": {
                    "Enabled": False,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Timelapse movie rendering :clapper:",
                    "Fallback": "Timelapse movie rendering: {print_name}",
                    "Color": "good",
                    "CaptureSnapshot": False,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": False,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportMovieStatus": True,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "MovieDone": {
                    "Enabled": False,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Timelapse movie rendering complete :movie_camera:",
                    "Fallback": "Timelapse movie rendering complete: {print_name}",
                    "Color": "good",
                    "CaptureSnapshot": False,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": False,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportMovieStatus": True,
                    "UploadMovie": False,
                    "UploadMovieLink": False,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
                "MovieFailed": {
                    "Enabled": False,
                    "ChannelOverride": "",
                    "Message": ":heavy_minus_sign:  Timelapse movie rendering failed :boom:",
                    "Fallback": "Timelapse movie rendering failed: {print_name}, Error: {error}",
                    "Color": "danger",
                    "CaptureSnapshot": False,
                    "ReportPrinterState": True,
                    "ReportEnvironment": False,
                    "ReportJobState": False,
                    "ReportJobOrigEstimate": False,
                    "ReportJobProgress": False,
                    "ReportMovieStatus": True,
                    "PushoverSound": "pushover",
                    "PushoverPriority": 0,
                    "CommandEnabled": False,
                    "CaptureCommandReturnCode": False,
                    "CaptureCommandOutput": False,
                    "Command": "",
                    "MinNotificationInterval": 0,
                },
            },
            "gcode_events": "",
            "timezones": "|".join(pytz.common_timezones),
            "timezone": "OS_Default",
            "eta_date_format": "hh:mm tt <fuzzy date>",
        }

    def get_settings_restricted_paths(self):
        return dict(
            admin=[
                ["slack_apitoken_config", "api_token"],
                ["slack_webhook_config", "webhook_url"],
                ["pushbullet_config", "access_token"],
                ["pushover_config", "app_token"],
                ["rocketchat_config", "username"],
                ["rocketchat_config", "password"],
                ["matrix_config", "access_token"],
                ["s3_config", "AWSAccessKey"],
                ["s3_config", "AWSsecretKey"],
                ["s3_config", "s3Bucket"],
                ["minio_config", "AccessKey"],
                ["minio_config", "SecretKey"],
                ["minio_config", "Bucket"],
                ["minio_config", "Endpoint"],
                ["minio_config", "secure"],
                ["imgur_config", "client_id"],
                ["imgur_config", "client_secret"],
                ["imgur_config", "refresh_token"],
                ["imgur_config", "album_id"],
                ["additional_snapshot_urls"],
            ]
        )

    def get_settings_version(self):
        return 1

    def on_settings_save(self, data):
        try:
            octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
            self.update_progress_timer()
            self.update_heartbeat_timer()
            self.update_gcode_sent_listeners()
            self._slack_next_progress_snapshot_time = 0
        except Exception as e:
            self._logger.exception(
                "Error executing post-save actions, Error: " + str(e.message)
            )

    ##~ TemplatePlugin mixin

    ##def get_template_vars(self):
    ##   	return dict()

    def get_template_configs(self):
        return [dict(type="settings", custom_bindings=False)]

        ##~~ AssetPlugin mixin

    def get_assets(self):
        return dict(
            js=["js/Octoslack.js"],
            css=["css/Octoslack.css"],
            less=["less/Octoslack.less"],
        )

        ##~~ Softwareupdate hook

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://github.com/foosel/OctoPrint/wiki/Plugin:-Software-Update
        # for details.
        return dict(
            Octoslack=dict(
                displayName="Octoslack",
                displayVersion=self._plugin_version,
                # version check: github repository
                type="github_release",
                user="fraschetti",
                repo="Octoslack",
                current=self._plugin_version,
                # update method: pip
                pip="https://github.com/fraschetti/Octoslack/archive/{target_version}.zip",
            )
        )

        ##~~ StartupPlugin mixin

    def on_after_startup(self):
        self._logger.debug("Entering Slack RTM client init logic")
        self.start_rtm_client()
        self._logger.debug("Exited Slack RTM client init logic")

        self.update_gcode_sent_listeners()

        self.start_heartbeat_timer()

        ##~~ ShutdownPlugin mixin

    def on_shutdown(self):
        self.stop_rtm_client()

        self._logger.debug("Stopped Slack RTM client")

        self.stop_progress_timer()
        self.stop_heartbeat_timer()

        ##~~ PrintProgress mixin

    def on_print_progress(self, location, path, progress):
        try:
            progress_interval = int(
                self._settings.get(["supported_events"], merged=True)
                .get("Progress")
                .get("IntervalPct")
            )

            self._logger.debug(
                "Progress: "
                + str(progress)
                + " - IntervalPct: "
                + str(progress_interval)
            )

            if (
                progress > 0
                and progress < 100
                and progress_interval > 0
                and progress % progress_interval == 0
            ):
                self.handle_event(
                    "Progress", None, {"progress": progress}, False, False, None
                )
        except Exception as e:
            self._logger.exception(
                "Error processing progress event, Error: " + str(e.message)
            )

            ##~~ EventPlugin mixin

    def progress_timer_tick(self):
        self._logger.debug("Progress timer tick")
        self.handle_event("Progress", None, {}, False, False, None)

    print_cancel_time = None
    progress_timer = None
    heartbeat_timer = None

    def start_progress_timer(self):
        progress_event = self._settings.get(["supported_events"], merged=True).get(
            "Progress"
        )

        progress_notification_enabled = progress_event.get("Enabled")
        progress_command_enabled = progress_event.get("CommandEnabled")
        if not progress_notification_enabled and not progress_command_enabled:
            return

        progress_timer_interval = int(progress_event.get("IntervalTime"))

        if (
            progress_timer_interval > 0
            and (self._printer.is_printing() or self._printer.is_paused())
            and not self._printer.is_ready()
        ):
            self._logger.debug(
                "Starting progress timer: " + str(progress_timer_interval) + "min(s)"
            )
            self.progress_timer = RepeatedTimer(
                progress_timer_interval * 60, self.progress_timer_tick, run_first=False
            )
            self.progress_timer.start()

    def update_progress_timer(self):
        restart = False

        progress_event = self._settings.get(["supported_events"], merged=True).get(
            "Progress"
        )

        progress_notification_enabled = progress_event.get("Enabled")
        progress_command_enabled = progress_event.get("CommandEnabled")
        if not progress_notification_enabled and not progress_command_enabled:
            self.stop_progress_timer()
            return

        new_interval = int(progress_event.get("IntervalTime"))

        if self.progress_timer == None and new_interval > 0:
            restart = True
        else:
            existing_interval = 0
            if not self.progress_timer == None:
                existing_interval = self.progress_timer.interval
                ##OctoPrint wraps the interval in a lambda function
                if callable(existing_interval):
                    existing_interval = existing_interval()
                existing_interval = int(existing_interval / 60)

                self._logger.debug("New progress interval: " + str(new_interval))
                self._logger.debug(
                    "Previous progress interval: " + str(existing_interval)
                )

            if new_interval != existing_interval:
                restart = True

        if restart and new_interval > 0:
            self.stop_progress_timer()
            self.start_progress_timer()

    def stop_progress_timer(self):
        if not self.progress_timer == None:
            self._logger.debug("Stopping progress timer")
            self.progress_timer.cancel()
            self.progress_timer = None

    def heartbeat_timer_tick(self):
        self._logger.debug("Heartbeat timer tick")
        ##Color may be updated in process_slack_event
        self.handle_event("Heartbeat", None, {}, False, False, None)

    def start_heartbeat_timer(self):
        heartbeat_event = self._settings.get(["supported_events"], merged=True).get(
            "Heartbeat"
        )

        heartbeat_notification_enabled = heartbeat_event.get("Enabled")
        heartbeat_command_enabled = heartbeat_event.get("CommandEnabled")
        if not heartbeat_notification_enabled and not heartbeat_command_enabled:
            return

        heartbeat_timer_interval = int(heartbeat_event.get("IntervalTime"))
        if heartbeat_timer_interval > 0:
            self._logger.debug(
                "Starting heartbeat timer: " + str(heartbeat_timer_interval) + "min(s)"
            )
            self.heartbeat_timer = RepeatedTimer(
                heartbeat_timer_interval * 60,
                self.heartbeat_timer_tick,
                run_first=False,
            )
            self.heartbeat_timer.start()

    def update_heartbeat_timer(self):
        restart = False

        heartbeat_event = self._settings.get(["supported_events"], merged=True).get(
            "Heartbeat"
        )

        heartbeat_notification_enabled = heartbeat_event.get("Enabled")
        heartbeat_command_enabled = heartbeat_event.get("CommandEnabled")
        if not heartbeat_notification_enabled and not heartbeat_command_enabled:
            self.stop_heartbeat_timer()
            return

        new_interval = int(heartbeat_event.get("IntervalTime"))

        if self.heartbeat_timer == None and new_interval > 0:
            restart = True
        else:
            existing_interval = 0
            if not self.heartbeat_timer == None:
                existing_interval = self.heartbeat_timer.interval
                ##OctoPrint wraps the interval in a lambda function
                if callable(existing_interval):
                    existing_interval = existing_interval()
                existing_interval = int(existing_interval / 60)

                self._logger.debug("New heartbeat interval: " + str(new_interval))
                self._logger.debug(
                    "Previous heartbeat interval: " + str(existing_interval)
                )

            if new_interval != existing_interval:
                restart = True

        if restart and new_interval > 0:
            self.stop_heartbeat_timer()
            self.start_heartbeat_timer()

    def stop_heartbeat_timer(self):
        if not self.heartbeat_timer == None:
            self._logger.debug("Stopping heartbeat timer")
            self.heartbeat_timer.cancel()
            self.heartbeat_timer = None

    last_trigger_height = 0.0

    def process_zheight_change(self, payload):
        if not self._printer.is_printing():
            return False
        if not "new" in payload:
            return False

        height_interval = float(
            self._settings.get(["supported_events"], merged=True)
            .get("Progress")
            .get("IntervalHeight")
        )
        if height_interval <= 0:
            return False

        new = payload["new"]
        if new <= self.last_trigger_height:
            return False

        if new >= (self.last_trigger_height + height_interval):
            self._logger.debug(
                "ZChange interval: "
                + str(height_interval)
                + ", Last trigger height: "
                + str(self.last_trigger_height)
                + ", Payload: "
                + json.dumps(payload)
            )
            self.last_trigger_height = new
            return True

        return False

    def on_event(self, event, payload):
        self.handle_event(event, None, payload, False, False, None)

    event_last_processed = {}  ##event --> timestamp map

    def handle_event(
        self,
        event,
        channel_override,
        payload,
        override_notification_enabled_check,
        override_command_enabled_check,
        event_settings_overrides,
    ):
        try:
            if event == "PrintCancelled":
                self.stop_progress_timer()
                self.print_cancel_time = time.time()
                self._bot_progress_last_req = None
                with self._bot_progress_last_snapshot_queue.mutex:
                    self._bot_progress_last_snapshot_queue.queue.clear()
            elif event == "PrintFailed":
                self.stop_progress_timer()
                self._bot_progress_last_req = None
                with self._bot_progress_last_snapshot_queue.mutex:
                    self._bot_progress_last_snapshot_queue.queue.clear()

                ignore_cancel_fail_event = self._settings.get(
                    ["ignore_cancel_fail_event"], merged=True
                )
                ##If the ignore flag is enabled and we've seen a PrintCancelled within 30s, ignore the PrintFailed event
                if (
                    ignore_cancel_fail_event
                    and not self.print_cancel_time == None
                    and (time.time() - self.print_cancel_time) < 30
                ):
                    self._logger.debug(
                        "Ignoring PrintFailed event within accecptable window of a PrintCancelled event"
                    )
                    return
            elif event == "PrintStarted":
                self.start_progress_timer()
                self.print_cancel_time = None
                self.last_trigger_height = 0.0
                self._bot_progress_last_req = None
                with self._bot_progress_last_snapshot_queue.mutex:
                    self._bot_progress_last_snapshot_queue.queue.clear()
                self._slack_next_progress_snapshot_time = 0
            elif event == "PrintDone":
                self.stop_progress_timer()
                self.print_cancel_time = None
                self._bot_progress_last_req = None
                with self._bot_progress_last_snapshot_queue.mutex:
                    self._bot_progress_last_snapshot_queue.queue.clear()
            elif event == "ZChange":
                if self.process_zheight_change(payload):
                    self.handle_event("Progress", None, payload, False, False, None)
                return
            elif event == "MetadataAnalysisFinished":
                ##If using OctoPrint-PrintTimeGenius, don't register the finished event until its actually done
                if payload and "result" in payload:
                    analysis_result = payload["result"]
                    if (
                        "analysisPending" in analysis_result
                        and analysis_result["analysisPending"]
                    ):
                        return
            elif event == "plugin_octolapse_movie_done":
                self._logger.debug("Got Octolapse 'Timelapse Done' Event. Forwarding to 'MovieDone'")
                self.handle_event("MovieDone",
                                  channel_override,
                                  payload,
                                  override_notification_enabled_check,
                                  override_command_enabled_check,
                                  event_settings_overrides
                )
                return

            supported_events = self._settings.get(["supported_events"], merged=True)
            if supported_events == None or not event in supported_events:
                return

            event_settings = supported_events[event]

            if event_settings == None:
                return

            if not event_settings_overrides == None:
                for key in event_settings_overrides:
                    event_settings[key] = event_settings_overrides[key]

            notification_enabled = (
                override_notification_enabled_check or event_settings["Enabled"]
            )
            command_enabled = (
                override_command_enabled_check or event_settings["CommandEnabled"]
            )

            if not notification_enabled and not command_enabled:
                return

            if payload == None:
                payload = {}

            self._logger.debug(
                "Event: "
                + event
                + ", NotificationEnabled: "
                + str(notification_enabled)
                + ", CommandEnabled: "
                + str(command_enabled)
                + ", Payload: "
                + str(payload)
            )

            last_processed_key = event
            if event == "GcodeEvent":
                last_processed_key = event + "_" + event_settings["InternalName"]

            if (
                "MinNotificationInterval" in event_settings
                and last_processed_key in self.event_last_processed
                and not override_notification_enabled_check
            ):
                min_notification_interval = int(
                    event_settings["MinNotificationInterval"]
                )
                if min_notification_interval > 0:
                    prev_timestamp = self.event_last_processed[last_processed_key]
                    now = time.time()
                    if now < (prev_timestamp + (min_notification_interval * 60)):
                        self._logger.debug(
                            "Ignoring "
                            + event
                            + " event to satisfy min notification interval"
                        )
                        return

            self.event_last_processed[last_processed_key] = time.time()

            self.process_slack_event(
                event,
                event_settings,
                channel_override,
                payload,
                notification_enabled,
                command_enabled,
            )
        except Exception as e:
            self._logger.exception(
                "Error processing event: " + event + ", Error: " + str(e.message)
            )

    def get_origin_text(self, print_origin):
        if print_origin == "local":
            return "OctoPrint"
        elif print_origin == "sdcard":
            return "SD Card"
        elif print_origin == None:
            return "N/A"

        return print_origin

    def process_slack_event(
        self,
        event,
        event_settings,
        channel_override,
        event_payload,
        notification_enabled,
        command_enabled,
    ):
        fallback = ""
        pretext = ""
        title = ""
        text = ""
        text_arr = []
        color = ""
        fields = []
        footer = ""
        command = ""
        includeSnapshot = False
        reportPrinterState = False
        reportEnvironment = False
        reportJobState = False
        reportJobOrigEstimate = False
        reportJobProgress = False
        reportMovieStatus = False
        reportFinalPrintTime = False
        includeSupportedCommands = False
        bold_text_start, bold_text_end, name_val_sep, newline = (
            self.get_formatting_elements()
        )

        if (
            channel_override == None or len(channel_override.strip()) == 0
        ) and "ChannelOverride" in event_settings:
            channel_override = event_settings["ChannelOverride"]
        if "Fallback" in event_settings:
            fallback = event_settings["Fallback"]
        if "Message" in event_settings:
            pretext = event_settings["Message"]
        if "Color" in event_settings:
            color = event_settings["Color"]
        if "Command" in event_settings:
            command = event_settings["Command"]
        if "CaptureSnapshot" in event_settings:
            includeSnapshot = event_settings["CaptureSnapshot"]
        if "ReportPrinterState" in event_settings:
            reportPrinterState = event_settings["ReportPrinterState"]
        if "ReportEnvironment" in event_settings:
            reportEnvironment = event_settings["ReportEnvironment"]
        if "ReportJobState" in event_settings:
            reportJobState = event_settings["ReportJobState"]
        if "ReportJobOrigEstimate" in event_settings:
            reportJobOrigEstimate = event_settings["ReportJobOrigEstimate"]
        if "ReportJobProgress" in event_settings:
            reportJobProgress = event_settings["ReportJobProgress"]
        if "ReportMovieStatus" in event_settings:
            reportMovieStatus = event_settings["ReportMovieStatus"]
        if "ReportFinalPrintTime" in event_settings:
            reportFinalPrintTime = event_settings["ReportFinalPrintTime"]
        if "IncludeSupportedCommands" in event_settings:
            includeSupportedCommands = event_settings["IncludeSupportedCommands"]

        replacement_params = {
            "{print_name}": "N/A",
            "{pct_complete}": "N/A",
            "{current_z}": "N/A",
            "{elapsed_time}": "N/A",
            "{remaining_time}": "N/A",
            "{eta}": "N/A",
            "{error}": "N/A",
            "{cmd}": "N/A",
            "{ip_address}": "N/A",
            "{hostname}": "N/A",
            "{fqdn}": "N/A",
            "{printer_status}": "N/A",
        }

        printer_data = self._printer.get_current_data()
        printer_state = printer_data["state"]
        job_state = printer_data["job"]
        z_height = printer_data["currentZ"]
        progress_state = printer_data["progress"]

        file_name = job_state["file"]["name"]
        if file_name == None:
            file_name = "N/A"

        ##Override the print_name variable for the analysis events
        if event == "MetadataAnalysisStarted" or event == "MetadataAnalysisFinished":
            if "name" in event_payload:
                file_name = event_payload["name"]
            else:
                file_name = "N/A"

            print_origin = "N/A"
            if "origin" in event_payload:
                print_origin = self.get_origin_text(event_payload["origin"])

            fileStr = file_name + " (via " + print_origin + ")"

            text_arr.append(
                bold_text_start + "File" + bold_text_end + name_val_sep + fileStr
            )

        if event == "MetadataAnalysisFinished":
            estimated_print_time = "N/A"
            analysis_print_time = None
            compensated_print_time = None

            if "result" in event_payload:
                analysis_result = event_payload["result"]

                if "estimatedPrintTime" in analysis_result:
                    estimated_print_time = self.format_duration(
                        analysis_result["estimatedPrintTime"]
                    )

                if "analysisPrintTime" in analysis_result:
                    analysis_print_time = self.format_duration(
                        analysis_result["analysisPrintTime"]
                    )

                if "compensatedPrintTime" in analysis_result:
                    compensated_print_time = self.format_duration(
                        analysis_result["compensatedPrintTime"]
                    )

            if analysis_print_time and compensated_print_time:
                text_arr.append(
                    bold_text_start
                    + "Analyzed print time estimate"
                    + bold_text_end
                    + name_val_sep
                    + analysis_print_time
                )

                text_arr.append(
                    bold_text_start
                    + "Compensated print time estimate"
                    + bold_text_end
                    + name_val_sep
                    + compensated_print_time
                )
            else:
                text_arr.append(
                    bold_text_start
                    + "Estimated print time"
                    + bold_text_end
                    + name_val_sep
                    + estimated_print_time
                )

        replacement_params["{print_name}"] = file_name

        z_height_str = ""
        if not z_height == None and not z_height == "None":
            z_height_str = ", Nozzle Height: " + "{0:.2f}".format(z_height) + "mm"

        replacement_params["{current_z}"] = z_height_str

        printer_text = printer_state["text"]
        if not printer_text == None:
            printer_text = printer_text.strip()
        replacement_params["{printer_status}"] = printer_text

        self._logger.debug("Printer data: " + str(printer_data))

        ##Override Heartbeat event color if printer is in an error state
        if event == "Heartbeat" and self._printer.is_closed_or_error():
            color = "danger"

        if reportJobState:
            print_origin = job_state["file"]["origin"]
            print_origin = self.get_origin_text(print_origin)

            file_bytes = job_state["file"]["size"]
            if file_bytes == None:
                file_bytes = 0
            file_size = octoprint.util.get_formatted_size(file_bytes)

            if file_bytes > 0:
                jobStateStr = (
                    file_name + " (" + file_size + " via " + print_origin + ")"
                )
            else:
                jobStateStr = file_name

            text_arr.append(
                bold_text_start + "File" + bold_text_end + name_val_sep + jobStateStr
            )

        if reportJobOrigEstimate:
            estimatedPrintTime = None
            if "lastPrintTime" in job_state:
                estimatedPrintTime = job_state["lastPrintTime"]
            if estimatedPrintTime == None:
                estimatedPrintTime = job_state["estimatedPrintTime"]
            if estimatedPrintTime == None:
                estimatedPrintTime = "N/A"
                estimatedPrintTimeStr = "N/A"
            else:
                estimatedPrintTimeStr = self.format_duration(estimatedPrintTime)

            if self._printer.is_printing():
                estimatedFinish = self.format_eta(estimatedPrintTime)
            else:
                estimatedFinish = "N/A"

            replacement_params["{remaining_time}"] = estimatedPrintTimeStr
            replacement_params["{eta}"] = estimatedFinish

            text_arr.append(
                bold_text_start
                + "Estimated print time"
                + bold_text_end
                + name_val_sep
                + estimatedPrintTimeStr
            )

            if event != "PrintDone" and self._printer.is_printing():
                text_arr.append(
                    bold_text_start
                    + "ETA"
                    + bold_text_end
                    + name_val_sep
                    + estimatedFinish
                )

        if event == "Progress" and "progress" in event_payload:
            pct_complete = event_payload["progress"]
        else:
            pct_complete = progress_state["completion"]
        if not pct_complete == None:
            pct_complete = str(int(pct_complete)) + "%"
        if not pct_complete == None:
            replacement_params["{pct_complete}"] = pct_complete

        elapsed = progress_state["printTime"]
        time_left = progress_state["printTimeLeft"]

        elapsed_str = self.format_duration(elapsed)

        replacement_params["{elapsed_time}"] = elapsed_str

        ##Use existing remaining time if it's already been set
        if replacement_params["{remaining_time}"] == "N/A":
            time_left_str = self.format_duration(time_left)
            replacement_params["{remaining_time}"] = time_left_str
        else:
            time_left_str = replacement_params["{remaining_time}"]

        ##Use existing ETA if it's already been set
        if replacement_params["{eta}"] == "N/A" and self._printer.is_printing():
            eta_str = self.format_eta(time_left)
            replacement_params["{eta}"] = eta_str
        else:
            eta_str = replacement_params["{eta}"]

        if reportJobProgress and not pct_complete == None:
            text_arr.append(
                bold_text_start + "Elapsed" + bold_text_end + name_val_sep + elapsed_str
            )
            text_arr.append(
                bold_text_start
                + "Remaining"
                + bold_text_end
                + name_val_sep
                + time_left_str
            )

            if self._printer.is_printing():
                text_arr.append(
                    bold_text_start + "ETA" + bold_text_end + name_val_sep + eta_str
                )

            ##Is rendered as a footer so it's safe to always include this
        if reportPrinterState:
            printer_temps = self._printer.get_current_temperatures()

            temp_str = ""
            if not printer_temps == None and "bed" in printer_temps:
                temp_str = ""
                for key in printer_temps:
                    if key == "bed":
                        temp_str += (
                            ", Bed: "
                            + str(printer_temps["bed"]["actual"])
                            + unichr(176)
                            + "C/"
                            + str(printer_temps["bed"]["target"])
                            + unichr(176)
                            + "C"
                        )
                    elif key.startswith("tool"):
                        nozzle_name = "Nozzle"
                        printer_profile = (
                            self._printer_profile_manager.get_current_or_default()
                        )
                        shared_nozzle = printer_profile["extruder"]["sharedNozzle"]
                        nozzle_number = key[4:]

                        if shared_nozzle and nozzle_number and nozzle_number != "0":
                            # only show the first nozzle if they are 'shared'
                            self._logger.debug(
                                "Skipping nozzle {} because it is shared.".format(
                                    nozzle_number
                                )
                            )
                        else:

                            if len(printer_temps) > 2:
                                nozzle_name += key[4:]

                            temp_str += (
                                ", "
                                + nozzle_name
                                + ": "
                                + str(printer_temps[key]["actual"])
                                + unichr(176)
                                + "C/"
                                + str(printer_temps[key]["target"])
                                + unichr(176)
                                + "C"
                            )

            footer = "Printer: " + printer_text + temp_str + z_height_str

        ##Skip this if not sending a notification (not current available for command execution)
        if notification_enabled and self._settings.get(
            ["include_raspi_temp"], merged=True
        ):

            rpi_tmp = None
            try:
                p = run("/opt/vc/bin/vcgencmd measure_temp", stdout=Capture())
                rpi_tmp = p.stdout.text

                if not rpi_tmp == None and rpi_tmp.startswith("temp="):
                    rpi_tmp = rpi_tmp.strip()
                    rpi_tmp = rpi_tmp[5:-2]
                else:
                    rpi_tmp = None
            except Exception as e:
                if type(e) == ValueError:
                    self._logger.error(
                        "Unable to execute Raspberry Pi command (/opt/vc/bin/vcgencmd): "
                        + e.message
                    )
                else:
                    self._logger.exception(
                        "Error reading Raspberry Pi temp - Error: " + str(e)
                    )

            if not rpi_tmp == None:
                if len(footer) > 0:
                    footer += ", "

                footer += "RasPi: " + rpi_tmp + unichr(176) + "C"

        if reportEnvironment:
            if len(footer) > 0:
                footer += ", "

            footer += "OctoPrint: " + get_octoprint_version_string()
            footer += ", " + self._plugin_name + ": v" + self._plugin_version

        final_time = "N/A"
        if event == "PrintDone" and "time" in event_payload:
            final_time = self.format_duration(event_payload["time"])
            replacement_params["{elapsed_time}"] = final_time

        if reportFinalPrintTime:
            text_arr.append(
                bold_text_start
                + "Final print time"
                + bold_text_end
                + name_val_sep
                + final_time
            )

        if event == "GcodeEvent" and "cmd" in event_payload:
            replacement_params["{cmd}"] = event_payload["cmd"]

        if reportMovieStatus:
            movie_name = None
            print_filename = None

            if "movie_basename" in event_payload:
                movie_name = event_payload["movie_basename"]
            if "gcode" in event_payload:
                print_filename = event_payload["gcode"]

            if not movie_name == None:
                text_arr.append(
                    bold_text_start
                    + "Movie"
                    + bold_text_end
                    + name_val_sep
                    + movie_name
                )
            if not print_filename == None:
                text_arr.append(
                    bold_text_start
                    + "Print job"
                    + bold_text_end
                    + name_val_sep
                    + print_filename
                )

        ips = self.get_ips()
        ips_str = ", ".join(ips)
        replacement_params["{ip_address}"] = ips_str
        replacement_params["{hostname}"] = self.get_hostname()
        replacement_params["{fqdn}"] = self.get_fqdn()

        if includeSupportedCommands:
            enabled_commands = self._settings.get(
                ["slack_rtm_enabled_commands"], merged=True
            )

            unauthorized_reaction = self._settings.get(
                ["slack_apitoken_config"], merged=True
            ).get("commands_unauthorized_reaction")

            authorized_users = self._settings.get(
                ["slack_rtm_authorized_users"], merged=True
            )
            if len(authorized_users.strip()) == 0:
                authorized_users = None

            if enabled_commands["help"]["enabled"]:
                text_arr.append(
                    bold_text_start
                    + "help"
                    + bold_text_end
                    + " - Displays this list of commands"
                    + (
                        " " + unauthorized_reaction
                        if authorized_users and enabled_commands["help"]["restricted"]
                        else ""
                    )
                )

            if enabled_commands["status"]["enabled"]:
                text_arr.append(
                    bold_text_start
                    + "status"
                    + bold_text_end
                    + " - Display the current print job status"
                    + (
                        " " + unauthorized_reaction
                        if authorized_users and enabled_commands["status"]["restricted"]
                        else ""
                    )
                )

            if enabled_commands["stop"]["enabled"]:
                text_arr.append(
                    bold_text_start
                    + "stop"
                    + bold_text_end
                    + " - Stop the current print"
                    + (
                        " " + unauthorized_reaction
                        if authorized_users and enabled_commands["stop"]["restricted"]
                        else ""
                    )
                )

            if enabled_commands["pause"]["enabled"]:
                text_arr.append(
                    bold_text_start
                    + "pause"
                    + bold_text_end
                    + " - Pause the current print"
                    + (
                        " " + unauthorized_reaction
                        if authorized_users and enabled_commands["pause"]["restricted"]
                        else ""
                    )
                )

            if enabled_commands["resume"]["enabled"]:
                text_arr.append(
                    bold_text_start
                    + "resume"
                    + bold_text_end
                    + " - Resume a paused print"
                    + (
                        " " + unauthorized_reaction
                        if authorized_users and enabled_commands["resume"]["restricted"]
                        else ""
                    )
                )

        error = None
        if "error" in event_payload:
            error = event_payload["error"]
        if not error == None:
            error = error.strip()
        if not error == None and len(error) > 0:
            text_arr.append(
                bold_text_start + "Error" + bold_text_end + name_val_sep + error
            )
            replacement_params["{error}"] = error

        if not text_arr == None and len(text_arr) > 0:
            text = newline.join(text_arr)

        for param in replacement_params:
            if not fallback == None:
                fallback = fallback.replace(param, replacement_params[param])
            if not pretext == None:
                pretext = pretext.replace(param, replacement_params[param])
            if not title == None:
                title = title.replace(param, replacement_params[param])
            if not text == None:
                text = text.replace(param, replacement_params[param])
            if not footer == None:
                footer = footer.replace(param, replacement_params[param])
            if not command == None:
                command = command.replace(param, shell_quote(replacement_params[param]))

            for field in fields:
                if "title" in field:
                    field["title"] = field["title"].replace(
                        param, replacement_params[param]
                    )
                if "value" in field:
                    field["value"] = field["value"].replace(
                        param, replacement_params[param]
                    )

        ##Execute custom command
        capture_command_returncode = False
        capture_command_output = False

        if (
            notification_enabled
            and "CaptureCommandReturnCode" in event_settings
            and event_settings["CaptureCommandReturnCode"]
        ):
            capture_command_returncode = True

        if (
            notification_enabled
            and "CaptureCommandOutput" in event_settings
            and event_settings["CaptureCommandOutput"]
        ):
            capture_command_output = True

        command_thread = None
        command_thread_rsp = None
        if command_enabled:
            command_thread_rsp = six.moves.queue.Queue()
            command_thread = threading.Thread(
                target=self.execute_command,
                args=(event, command, capture_command_output, command_thread_rsp),
            )
            command_thread.daemon = True
            command_thread.start()

        ##Execute notification send
        if notification_enabled:
            notification_thread = threading.Thread(
                target=self.send_slack_message,
                args=(
                    event,
                    event_settings,
                    event_payload,
                    channel_override,
                    fallback,
                    pretext,
                    title,
                    text,
                    color,
                    fields,
                    footer,
                    includeSnapshot,
                    replacement_params["{pct_complete}"],
                    command_thread,
                    command_thread_rsp,
                    capture_command_returncode,
                    capture_command_output,
                ),
            )
            notification_thread.daemon = True
            notification_thread.start()

    # Currrently only querying IPv4 although the library supports IPv6 as well
    def get_ips(self):
        ips = []
        try:
            for interface in netifaces.interfaces():
                for link in netifaces.ifaddresses(interface).get(netifaces.AF_INET, ()):
                    addr = link["addr"]
                    if addr == None or len(addr.strip()) == 0 or addr != "127.0.0.1":
                        ips.append(addr)
        except Exception as e:
            self._logger.exception("Failed to query IP address: " + str(e))

            ips = []
            ips.append("'IP detection error'")

        return ips

    def get_hostname(self):
        try:
            return socket.gethostname()
        except Exception as e:
            self._logger.exception("Failed to query hostname: " + str(e))

        return "Hostname detection error"

    def get_fqdn(self):
        try:
            return socket.getfqdn()
        except Exception as e:
            self._logger.exception("Failed to query fqdn: " + str(e))

        return "Fqdn detection error"

    slack_rtm_v2 = None
    slack_rtm_v2_registered = False

    def start_rtm_client(self):
        self.stop_rtm_client()

        if not self._settings.get(["slack_apitoken_config"], merged=True).get(
            "enable_commands"
        ):
            return

        connection_method = self.connection_method()
        if connection_method == None or connection_method != "APITOKEN":
            self._logger.debug("Slack RTM client not enabled")
            return

        slackAPIToken = self._settings.get(["slack_apitoken_config"], merged=True).get(
            "api_token"
        )
        if not slackAPIToken:
            self._logger.warn(
                "Cannot enable real time messaging client for responding to commands without an API Key"
            )
            return

        slackAPIToken = slackAPIToken.strip()

        self._logger.debug("Before Slack RTM client start")

        self.rtm_keep_running = True
        self.slack_rtm_v2 = None
        self.bot_user_id = None

        try:
            # Python2
            type(SlackClient)
            t = threading.Thread(target=self.execute_rtm_v1, args=(slackAPIToken,))
        except NameError:
            if not self.slack_rtm_v2_registered:
                self.slack_rtm_v2_registered = True

                dec_func = slack.RTMClient.run_on(event="open")
                dec_func(self.process_rtm_v2_message)

                dec_func = slack.RTMClient.run_on(event="close")
                dec_func(self.process_rtm_v2_message)

                dec_func = slack.RTMClient.run_on(event="message")
                dec_func(self.process_rtm_v2_message)

            # Python3
            t = threading.Thread(target=self.execute_rtm_v2, args=(slackAPIToken,))

        t.daemon = True
        t.start()

        self._logger.debug("After Slack RTM client start")

    def stop_rtm_client(self):
        self._logger.debug("Stopping Slack RTM client")
        self.rtm_keep_running = False

        if self.slack_rtm_v2:
            try:
                self.slack_rtm_v2.stop()
            except Exception as e:
                self._logger.exception(
                    "Failed to stop Slack RTM (v2) client: " + str(e)
                )

    def execute_rtm_v1(self, slackAPIToken):
        try:
            ping_interval = 30

            self._logger.debug("Starting Slack RTM (v1) wait loop")

            slack_rtm_v1 = None
            connection_attempt = 0
            next_ping = 0

            repeat_error_count = 0

            while self.rtm_keep_running:
                while slack_rtm_v1 == None or not slack_rtm_v1.server.connected:
                    try:
                        ##Reset read error count if we're reconnecting
                        repeat_error_count = 0

                        ##Roll over the counter to keep delay calculations under control
                        if connection_attempt > 100:
                            connection_attempt = 0

                        self._logger.debug(
                            "Attempting to connect Slack RTM (v1) API (iteration="
                            + str(connection_attempt)
                            + ")"
                        )

                        wait_delay = self.get_rtm_reconnect_delay(connection_attempt)

                        if wait_delay > 0:
                            self._logger.debug(
                                "Sleeping for "
                                + str(wait_delay)
                                + " seconds before attempting Slack RTM (v1) connection"
                            )
                            time.sleep(wait_delay)

                        slackAPIConnection = Slacker(
                            slackAPIToken, timeout=SLACKER_TIMEOUT
                        )

                        auth_rsp = slackAPIConnection.auth.test()
                        self._logger.debug(
                            "Slack RTM (v1) API Key auth test response: "
                            + json.dumps(auth_rsp.body)
                        )

                        if auth_rsp.successful == None or auth_rsp.successful == False:
                            self._logger.error(
                                "Slack RTM (v1) API Key auth test failed: "
                                + json.dumps(auth_rsp.body)
                            )
                            connection_attempt += 1
                            continue

                        self.bot_user_id = auth_rsp.body["user_id"]
                        self._logger.debug(
                            "Slack RTM (v1) Bot user id: " + self.bot_user_id
                        )

                        ##Slack's client doesn't expose the underlying websocket/socket
                        ##so we unfortunately need to rely on Python's GC to handle
                        ##the socket disconnect
                        slack_rtm_v1 = SlackClient(slackAPIToken)
                        if slack_rtm_v1.rtm_connect(with_team_state=False):
                            self._logger.debug(
                                "Successfully reconnected via Slack RTM (v1) API"
                            )
                            connection_attempt = 0
                            next_ping = time.time() + ping_interval
                        else:
                            self._logger.error(
                                "Failed to reconnect via Slack RTM (v1) API"
                            )
                            connection_attempt += 1
                    except Exception as e:
                        self._logger.error(
                            "Slack RTM (v1) API connection error (Exception): " + str(e)
                        )
                        connection_attempt += 1

                try:
                    if next_ping > 0 and time.time() >= next_ping:
                        ping_rsp = slack_rtm_v1.server.ping()
                        next_ping = time.time() + ping_interval

                    read_msgs = slack_rtm_v1.rtm_read()
                    if read_msgs:
                        for msg in read_msgs:
                            try:
                                self._logger.debug(
                                    "Slack RTM (v1) Message: " + str(msg)
                                )

                                if (
                                    msg.get("type") != "message"
                                    or msg.get("text") == None
                                ):
                                    continue

                                msg_text = msg.get("text", "")
                                msg_user = msg.get("user")
                                msg_channel = msg.get("channel")
                                msg_ts = msg.get("ts")

                                self._logger.debug(
                                    "Received Slack RTM (v1) Message - Text: "
                                    + str(msg_text)
                                    + ", User: "
                                    + str(msg_user)
                                    + ", Channel: "
                                    + str(msg_channel)
                                    + ", TS: "
                                    + str(msg_ts)
                                )

                                self.process_rtm_message(
                                    slackAPIToken,
                                    msg_text,
                                    msg_user,
                                    msg_channel,
                                    msg_ts,
                                )

                                ##Reset error counter if we've successfully processed a message
                                repeat_error_count = 0
                            except Exception as e:
                                self._logger.error(
                                    "Slack RTM (v1) message processing error: "
                                    + str(e),
                                    exc_info=e,
                                )
                    else:
                        time.sleep(0.5)
                except WebSocketConnectionClosedException as ce:
                    self._logger.error(
                        "Slack RTM (v1) API read error (WebSocketConnectionClosedException): "
                        + str(ce.message),
                        exc_info=ce,
                    )
                    time.sleep(1)
                    slack_rtm_v1 = None
                except Exception as e:
                    error_str = str(e)

                    self._logger.error(
                        "Slack RTM (v1) API read error (Exception): " + error_str
                    )

                    ##Ovserved errors on windows (WebSocketConnectionClosedException was not thrown)
                    ##HTTPSConnectionPool(host='slack.com', port=443): Max retries exceeded with url: /api/rtm.start (Caused by NewConnectionError('<urllib3.connection.VerifiedHTTPSConnection object at 0x000000000A6FB278>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed',))
                    ##[Errno 10054] An existing connection was forcibly closed by the remote host

                    if (
                        "Max retries exceeded" in error_str
                        or "NewConnectionError" in error_str
                        or "Errno 10054" in error_str
                        or "Errno 11001" in error_str
                        or "forcibly closed" in error_str
                    ):
                        self._logger.error(
                            "Slack RTM (v1) API experienced a fatal connection error. Resetting connection."
                        )
                        slack_rtm_v1 = None

                    time.sleep(1)
                    repeat_error_count += 1

                    if repeat_error_count >= 100:
                        self._logger.error(
                            "Slack RTM (v1) API experienced 100 back to back read errors. Resetting connection."
                        )
                        slack_rtm_v1 = None

            self._logger.debug("Finished Slack RTM (v1) read loop")
        except Exception as e:
            self._logger.exception(
                "Error in Slack RTM read loop, Error: " + str(e.message)
            )

    def get_rtm_reconnect_delay(self, iteration):
        max_delay = 1800  ##30 minutes

        try:
            delay = (2 ** iteration) * 5
            if delay <= 0 or delay > max_delay:
                return max_delay

            return delay
        except Exception as e:
            self._logger.exception(
                "Slack RTM reconnect delay calculation error (iteration="
                + str(iteration)
                + "), Error: "
                + str(e.message)
            )
            return max_delay

    def nonop_add_signal_handler(self, sig, callback, *args):
        return

    def execute_rtm_v2(self, slackAPIToken):
        try:
            self._logger.debug("Starting Slack RTM (v2) wait loop")

            slackAPIConnection = Slacker(slackAPIToken, timeout=SLACKER_TIMEOUT)

            auth_rsp = slackAPIConnection.auth.test()
            self._logger.debug(
                "Slack RTM (v2) API Key auth test response: "
                + json.dumps(auth_rsp.body)
            )

            if auth_rsp.successful == None or auth_rsp.successful == False:
                self._logger.error(
                    "Slack RTM (v2) API Key auth test failed: "
                    + json.dumps(auth_rsp.body)
                )
                self._logger.warn(
                    "Initial Slack RTM (v2) authentication failed but RTM client will still be started should the issue be resolved"
                )
            else:
                self.bot_user_id = auth_rsp.body["user_id"]
                self._logger.debug("Slack RTM (v2) Bot user id: " + self.bot_user_id)

            loop = asyncio.new_event_loop()
            self._logger.debug("Slack RTM (v2) event loop: " + str(loop))

            # asyncsio doesn't like running outside the main thread.
            # it's impossible to start an event loop on the main thread
            # via a plugin so I needed to patch the obvious bit that fails.
            # add_signal_handler serves to detect the service is being stopped
            # and will stop the event loop. This plugin hangles that
            # logic internally so while not ideal, we can 'disable it'
            funcType = type(loop.add_signal_handler)
            loop.add_signal_handler = funcType(self.nonop_add_signal_handler, loop)

            asyncio.set_event_loop(loop)

            self.slack_rtm_v2 = slack.RTMClient(
                token=slackAPIToken, ping_interval=30, loop=loop
            )
            self.slack_rtm_v2.start()

        except Exception as e:
            self._logger.exception(
                "Error in Slack RTM (v2) read loop, Error: " + str(e)
            )

    def process_rtm_v2_message(self, **payload):
        self._logger.debug("Slack RTM (v2) Message: " + str(payload))

        if "client_msg_id" not in payload["data"] or "text" not in payload["data"]:
            self._logger.debug("Ignoring Slack RTM (v2) Message")
            return

        slackAPIToken = payload["rtm_client"].token

        data = payload["data"]
        msg_text = data["text"]
        msg_user = data["user"]
        msg_channel = data["channel"]
        msg_ts = data["ts"]

        self._logger.debug(
            "Received Slack RTM (v2) Message - Text: "
            + msg_text
            + ", User: "
            + msg_user
            + ", Channel: "
            + msg_channel
            + ", TS: "
            + str(msg_ts)
        )

        self.process_rtm_message(slackAPIToken, msg_text, msg_user, msg_channel, msg_ts)

    def process_rtm_message(
        self, slackAPIToken, msg_text, msg_user, msg_channel, msg_ts
    ):
        self._logger.debug(
            "Processing Slack RTM Message - Text: "
            + str(msg_text)
            + ", User: "
            + str(msg_user)
            + ", Channel: "
            + str(msg_channel)
            + ", TS: "
            + str(msg_ts)
        )

        if not self._settings.get(["slack_apitoken_config"], merged=True).get(
            "enable_commands"
        ):
            return

        slack_identity_config = self._settings.get(["slack_identity"], merged=True)
        slack_as_user = slack_identity_config["existing_user"]
        alternate_bot_name = None

        if not slack_as_user:
            if "username" in slack_identity_config:
                alternate_bot_name = slack_identity_config["username"]

        alternate_bot_id = None
        if not alternate_bot_name == None and len(alternate_bot_name.strip()) > 0:
            alternate_bot_id = "@" + alternate_bot_name.strip()

        if (
            (self.bot_user_id == None and alternate_bot_id == None)
            or msg_text == None
            or len(msg_text.strip()) == 0
        ):
            return

        bot_id = "<@" + self.bot_user_id + ">"

        matched_id = None

        self._logger.debug(
            "Slack RTM message - Matching bot_id: "
            + str(bot_id)
            + " and alternate_bot_id: "
            + str(alternate_bot_id)
            + " against msg: "
            + str(msg_text)
        )

        if bot_id and bot_id in msg_text:
            matched_id = bot_id
        elif alternate_bot_id and alternate_bot_id in msg_text:
            matched_id = alternate_bot_id
        else:
            return

        source_username = self.get_slack_username(slackAPIToken, msg_user)
        self._logger.debug(
            "Slack RTM message source UserID: "
            + str(msg_user)
            + ", Username: "
            + str(source_username)
        )

        command = msg_text.split(matched_id)[1].strip().lower()

        reaction = ""

        positive_reaction = self._settings.get(
            ["slack_apitoken_config"], merged=True
        ).get("commands_positive_reaction")
        negative_reaction = self._settings.get(
            ["slack_apitoken_config"], merged=True
        ).get("commands_negative_reaction")
        processing_reaction = self._settings.get(
            ["slack_apitoken_config"], merged=True
        ).get("commands_processing_reaction")
        unauthorized_reaction = self._settings.get(
            ["slack_apitoken_config"], merged=True
        ).get("commands_unauthorized_reaction")

        if not positive_reaction == None:
            positive_reaction = positive_reaction.strip()
            if positive_reaction.startswith(":") and positive_reaction.endswith(":"):
                positive_reaction = positive_reaction[1:-1].strip()

        if not negative_reaction == None:
            negative_reaction = negative_reaction.strip()
            if negative_reaction.startswith(":") and negative_reaction.endswith(":"):
                negative_reaction = negative_reaction[1:-1].strip()

        if not processing_reaction == None:
            processing_reaction = processing_reaction.strip()
            if processing_reaction.startswith(":") and processing_reaction.endswith(
                ":"
            ):
                processing_reaction = processing_reaction[1:-1].strip()

        if not unauthorized_reaction == None:
            unauthorized_reaction = unauthorized_reaction.strip()
            if unauthorized_reaction.startswith(":") and unauthorized_reaction.endswith(
                ":"
            ):
                unauthorized_reaction = unauthorized_reaction[1:-1].strip()

        sent_processing_reaction = False

        enabled_commands = self._settings.get(
            ["slack_rtm_enabled_commands"], merged=True
        )
        authorized_users = self._settings.get(
            ["slack_rtm_authorized_users"], merged=True
        )

        authorized_user_lookup = {}
        for user in authorized_users.split(","):
            user = user.strip().lower()
            if len(user) > 0:
                authorized_user_lookup[user] = True

        if len(authorized_user_lookup) == 0:
            authorized_user_lookup = None

        authorized = self.is_rtm_command_authorized_user(
            authorized_user_lookup, source_username, enabled_commands, command
        )

        if command == "help" and enabled_commands["help"]["enabled"]:
            self._logger.info(
                "Slack RTM - help command - user: "
                + source_username
                + ", authorized: "
                + str(authorized)
            )
            if not authorized:
                reaction = unauthorized_reaction
            else:
                self.handle_event("Help", msg_channel, {}, True, False, None)
                reaction = positive_reaction
        elif command == "stop" and enabled_commands["stop"]["enabled"]:
            self._logger.info(
                "Slack RTM - stop command - user: "
                + source_username
                + ", authorized: "
                + str(authorized)
            )
            if not authorized:
                reaction = unauthorized_reaction
            elif self._printer.is_printing():
                ##Send processing reaction
                sent_processing_reaction = True
                self.add_message_reaction(
                    slackAPIToken, msg_channel, msg_ts, processing_reaction, False
                )

                self._printer.cancel_print()
                reaction = positive_reaction
            else:
                reaction = negative_reaction
        elif command == "pause" and enabled_commands["pause"]["enabled"]:
            self._logger.info(
                "Slack RTM - pause command - user: "
                + source_username
                + ", authorized: "
                + str(authorized)
            )
            if not authorized:
                reaction = unauthorized_reaction
            elif self._printer.is_printing():
                ##Send processing reaction
                sent_processing_reaction = True

                self.add_message_reaction(
                    slackAPIToken, msg_channel, msg_ts, processing_reaction, False
                )
                self._printer.toggle_pause_print()
                reaction = positive_reaction
            else:
                reaction = negative_reaction
        elif command == "resume" and enabled_commands["resume"]["enabled"]:
            self._logger.info(
                "Slack RTM - resume command - user: "
                + source_username
                + ", authorized: "
                + str(authorized)
            )
            if not authorized:
                reaction = unauthorized_reaction
            elif self._printer.is_paused():
                ##Send processing reaction
                sent_processing_reaction = True
                self.add_message_reaction(
                    slackAPIToken, msg_channel, msg_ts, processing_reaction, False
                )

                self._printer.toggle_pause_print()
                reaction = positive_reaction
            else:
                reaction = negative_reaction
        elif command == "status" and enabled_commands["status"]["enabled"]:
            ##Send processing reaction
            self._logger.info(
                "Slack RTM - status command - user: "
                + source_username
                + ", authorized: "
                + str(authorized)
            )
            if not authorized:
                reaction = unauthorized_reaction
            else:
                sent_processing_reaction = True

                self.add_message_reaction(
                    slackAPIToken, msg_channel, msg_ts, processing_reaction, False
                )
                self.handle_event("Progress", msg_channel, {}, True, False, None)
                reaction = positive_reaction

        else:
            reaction = negative_reaction

        self.add_message_reaction(slackAPIToken, msg_channel, msg_ts, reaction, False)

        ##Remove the processing reaction if it was previously added
        if sent_processing_reaction:
            self.add_message_reaction(
                slackAPIToken, msg_channel, msg_ts, processing_reaction, True
            )

    def is_rtm_command_authorized_user(
        self, authorized_users, username, enabled_commands, command
    ):
        if authorized_users == None or len(authorized_users) == 0:
            return True

        ##The failed command will be handled later
        if not command in enabled_commands:
            return True

        auth_required = enabled_commands[command]["restricted"]
        if not auth_required:
            return True

        username = username.strip().lower()
        if username in authorized_users:
            return True

        return False

    def get_slack_username(self, slackAPIToken, userid):
        try:
            if userid == None:
                return

            userid = userid.strip()

            if len(userid) == 0:
                return

            slackAPIConnection = Slacker(slackAPIToken, timeout=SLACKER_TIMEOUT)

            self._logger.debug(
                "Retrieving username for Slack RTM message - User ID: " + userid
            )

            user_info_rsp = slackAPIConnection.users.info(userid)

            self._logger.debug(
                "Slack user info rsp for User ID: "
                + userid
                + ", Response: "
                + json.dumps(user_info_rsp.body)
            )

            return user_info_rsp.body["user"]["name"]
        except Exception as e:
            self._logger.exception(
                "Error retrieving username for Slack RTM message - User ID: "
                + userid
                + ", Error: "
                + str(e.message)
            )

    def add_message_reaction(self, slackAPIToken, channel, timestamp, reaction, remove):
        try:
            if reaction == None:
                return

            reaction = reaction.strip()

            if len(reaction) == 0:
                return

            slackAPIConnection = Slacker(slackAPIToken, timeout=SLACKER_TIMEOUT)

            self._logger.debug(
                "Sending Slack RTM reaction - Channel: "
                + channel
                + ", Timestamp: "
                + timestamp
                + ", Reaction: "
                + reaction
                + ", Remove: "
                + str(remove)
            )

            if remove:
                reaction_rsp = slackAPIConnection.reactions.remove(
                    channel=channel, timestamp=timestamp, name=reaction
                )
            else:
                reaction_rsp = slackAPIConnection.reactions.add(
                    channel=channel, timestamp=timestamp, name=reaction
                )

            if reaction_rsp.successful == None or reaction_rsp.successful == False:
                self._logger.debug(
                    "Slack RTM send reaction failed - Channel: "
                    + channel
                    + ", Timestamp: "
                    + timestamp
                    + ", Reaction: "
                    + reaction
                    + ", Remove: "
                    + str(remove)
                    + json.dumps(reaction_rsp.body)
                )
            else:
                self._logger.debug(
                    "Successfully sent Slack RTM reaction - Channel: "
                    + channel
                    + ", Timestamp: "
                    + timestamp
                    + ", Reaction: "
                    + reaction
                    + ", Remove: "
                    + str(remove)
                )
        except Exception as e:
            self._logger.exception(
                "Error sending Slack RTM reaction - Channel: "
                + channel
                + ", Timestamp: "
                + timestamp
                + ", Reaction: "
                + reaction
                + ", Remove: "
                + str(remove)
                + ", Error: "
                + str(e.message)
            )

    def delete_file(self, filename):
        max_attempts = 3

        if filename == None or len(filename.strip()) == 0:
            return

        for attempt_no in range(1, max_attempts + 1):
            try:
                delay = (attempt_no - 1) * 0.5
                if delay > 0:
                    self._logger.debug(
                        "Sleeping "
                        + str(delay)
                        + "ms before next deletion attempt of local file (attempt #"
                        + str(attempt_no)
                        + "): "
                        + filename
                    )
                    time.sleep(delay)

                self._logger.debug(
                    "Deleting local file (attempt #"
                    + str(attempt_no)
                    + "): "
                    + filename
                )
                os.remove(filename)

                if not os.path.exists(filename):
                    self._logger.debug(
                        "Deletion of local file confirmed (attempt #"
                        + str(attempt_no)
                        + "): "
                        + filename
                    )
                    return
            except Exception as e:
                self._logger.error(
                    "Error attempting deletion of local file (attempt #"
                    + str(attempt_no)
                    + "): "
                    + filename,
                    e,
                )

        self._logger.debug(
            "Deletion of local file failed after "
            + str(max_attempts)
            + " attempts: "
            + filename
        )

    def connection_method(self):
        return self._settings.get(["connection_method"], merged=True)

    def mattermost_mode(self):
        return self._settings.get(["mattermost_compatability_mode"], merged=True)

    def get_formatting_elements(self):
        ##returns bold formatting str, key/value separator (often used when bold can't be used), newline
        connection_method = self.connection_method()
        if connection_method == "WEBHOOK" and self.mattermost_mode():
            return "**", "**", " ", "\n"
        elif connection_method == "WEBHOOK" or connection_method == "APITOKEN":
            return "*", "*", " ", "\n"
        elif connection_method == "PUSHOVER":
            return "<b>", "</b>", " ", "\n"
        elif connection_method == "ROCKETCHAT":
            return "*", "*", " ", "\n"
        elif connection_method == "MATRIX":
            return "<b>", "</b>", " ", "<br/>\n"
        elif connection_method == "DISCORD":
            return "**", "**", " ", "\n"
        elif connection_method == "TEAMS":
            return "**", "**", " ", "\n\n"

        return "", "", ": ", "\n"

    def format_eta(self, seconds):
        """For a given seconds to complete, returns an ETA string for humans.
        """
        if seconds is None or seconds == "N/A":
            return "N/A"

        tz_config = self._settings.get(["timezone"], merged=True)

        local_now = datetime.datetime.now()
        local_eta = local_now + datetime.timedelta(seconds=seconds)

        ##Return local OS timestamp
        if not tz_config or tz_config == "OS_Default":
            eta = local_eta
            now = local_now
        else:
            ##Generate TZ adjusted timestamp
            tz = pytz.timezone(tz_config)
            utc_time = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
            now = utc_time.astimezone(tz)
            eta = now + datetime.timedelta(seconds=seconds)

        ##Config UI string, not an actual python date/time format string
        selected_date_format = self._settings.get(["eta_date_format"], merged=True)

        if selected_date_format == "HH:mm <fuzzy date>":
            return "%s %s" % (eta.strftime("%H:%M"), self.humanize_day_delta(now, eta))
        elif selected_date_format == "hh:mm tt <fuzzy date>":
            return "%s %s" % (
                eta.strftime("%I:%M %p"),
                self.humanize_day_delta(now, eta),
            )
        elif selected_date_format == "MM/dd/yyyy HH:mm":
            return eta.strftime("%m/%d/%Y %H:%M")
        elif selected_date_format == "dd/MM/yyyy HH:mm":
            return eta.strftime("%d/%m/%Y %H:%M")
        elif selected_date_format == "MM/dd/yyyy hh:mm tt":
            return eta.strftime("%m/%d/%Y %I:%M %p")
        elif selected_date_format == "dd/MM/yyyy hh:mm tt":
            return eta.strftime("%d/%m/%Y %I:%M %p")
        else:
            return eta.strftime("%Y-%m-%d %H:%M")

    def humanize_day_delta(self, now, eta):
        new_now = datetime.date(now.year, now.month, now.day)
        new_eta = datetime.date(eta.year, eta.month, eta.day)

        delta_days = (new_eta - new_now).days

        if delta_days == -1:
            return "yesterday"
        elif delta_days == 0:
            return "today"
        elif delta_days == 1:
            return "tomorrow"
        else:
            return eta.strftime("%b %d")

    def format_duration(self, seconds):
        time_format = self._settings.get(["time_format"], merged=True)
        if seconds == None:
            return "N/A"

        delta = datetime.timedelta(seconds=seconds)

        time_format = self._settings.get(["time_format"], merged=True)
        if time_format == "FUZZY":
            return humanize.naturaldelta(delta)
        elif time_format == "EXACT":
            return octoprint.util.get_formatted_timedelta(delta)
        else:
            return self.humanize_duration(seconds)

    def humanize_duration(self, total_seconds):
        total_days = int(total_seconds / 86400)
        total_seconds -= total_days * 86400

        total_hours = int(total_seconds / 3600)
        total_seconds -= total_hours * 3600

        total_minutes = int(total_seconds / 60)
        total_seconds = int(total_seconds - (total_minutes * 60))

        time_str = ""

        if total_days > 0:
            if total_days == 1:
                time_str += "1 day"
            else:
                time_str += str(total_days) + " days"

        if total_hours > 0 or len(time_str) > 0:
            if len(time_str) > 0:
                time_str += " "

            if total_hours != 1:
                time_str += str(total_hours) + " hours"
            else:
                time_str += "1 hour"

        if total_minutes > 0 or len(time_str) > 0:
            if len(time_str) > 0:
                time_str += " "

            if total_minutes != 1:
                time_str += str(total_minutes) + " minutes"
            else:
                time_str += "1 minute"

                ##Only display seconds if nothing else has been displayed or if there is less than 10 minutes left
        if len(time_str) == 0 or (
            total_days == 0 and total_hours == 0 and total_minutes < 10
        ):
            if len(time_str) > 0:
                time_str += " "

            if total_seconds != 1:
                time_str += str(total_seconds) + " seconds"
            else:
                time_str += "1 second"

        return time_str

    _bot_progress_last_req = None
    _bot_progress_last_snapshot_queue = six.moves.queue.Queue()
    _slack_next_progress_snapshot_time = 0

    def execute_command(self, event, command, capture_output, command_rsp):
        self._logger.debug(
            "Executing command for event: " + event + ' - "' + command + '"'
        )

        return_code = None
        command_output = None
        error_msg = None

        try:
            execution_start = time.time()

            if capture_output:
                pipeline = run(command, stdout=Capture())
            else:
                pipeline = run(command)

            execution_elapsed = time.time() - execution_start

            pipeline_cmd = pipeline.commands[0]

            if capture_output:
                command_output = pipeline_cmd.stdout.text

            return_code = pipeline_cmd.returncode

            self._logger.debug(
                "Command executed in "
                + str(round(execution_elapsed, 2))
                + " seconds"
                + " - ReturnCode: "
                + str(return_code)
                + ", Command: "
                + command
                + ", Output: "
                + str(command_output)
            )
        except Exception as e:
            if hasattr(e, "message"):
                error_msg = e.message
            else:
                error_msg = str(e)

            self._logger.error(
                "Failed to execute command for event: " + event + " - " + error_msg
            )

        command_rsp.put(return_code)
        command_rsp.put(command_output)
        command_rsp.put(error_msg)

    def send_slack_message(
        self,
        event,
        event_settings,
        event_payload,
        channel_override,
        fallback,
        pretext,
        title,
        text,
        color,
        fields,
        footer,
        includeSnapshot,
        print_pct_complete,
        command_thread,
        command_thread_rsp,
        capture_command_returncode,
        capture_command_output,
    ):
        try:
            slackAPIToken = None
            slackWebHookUrl = None
            pushbulletAccessToken = None
            pushoverAppToken = None
            rocketChatServerURL = None
            rocketChatUsername = None
            rocketChatPassword = None
            matrixServerURL = None
            matrixAccessToken = None
            matrixUserID = None

            bold_text_start, bold_text_end, name_val_sep, newline = (
                self.get_formatting_elements()
            )

            connection_method = self.connection_method()
            progress_update_method = (
                self._settings.get(["supported_events"], merged=True)
                .get("Progress")
                .get("UpdateMethod")
            )
            slack_progress_snapshot_min_interval = 60 * int(
                self._settings.get(["supported_events"], merged=True)
                .get("Progress")
                .get("SlackMinSnapshotUpdateInterval")
            )
            self._logger.debug("Octoslack connection method: " + connection_method)

            if connection_method == "APITOKEN":
                slackAPIToken = self._settings.get(
                    ["slack_apitoken_config"], merged=True
                ).get("api_token")
                if not slackAPIToken == None:
                    slackAPIToken = slackAPIToken.strip()
                if slackAPIToken == None or len(slackAPIToken) == 0:
                    self._logger.error(
                        "Slack API connection not available, skipping message send"
                    )
                    return
            elif connection_method == "WEBHOOK":
                slackWebHookUrl = self._settings.get(
                    ["slack_webhook_config"], merged=True
                ).get("webhook_url")
                if not slackWebHookUrl == None:
                    slackWebHookUrl = slackWebHookUrl.strip()
                if slackWebHookUrl == None or len(slackWebHookUrl) == 0:
                    self._logger.error(
                        "Slack WebHook connection not available, skipping message send"
                    )
                    return
            elif connection_method == "PUSHBULLET":
                pushbulletAccessToken = self._settings.get(
                    ["pushbullet_config"], merged=True
                ).get("access_token")
                if not pushbulletAccessToken == None:
                    pushbulletAccessToken = pushbulletAccessToken.strip()
                if pushbulletAccessToken == None or len(pushbulletAccessToken) == 0:
                    self._logger.error(
                        "Pushbullet connection not available, skipping message send"
                    )
                    return
            elif connection_method == "PUSHOVER":
                pushoverAppToken = self._settings.get(
                    ["pushover_config"], merged=True
                ).get("app_token")
                if not pushoverAppToken == None:
                    pushoverAppToken = pushoverAppToken.strip()
                if pushoverAppToken == None or len(pushoverAppToken) == 0:
                    self._logger.error(
                        "Pushover connection not available, skipping message send"
                    )
                    return
            elif connection_method == "ROCKETCHAT":
                rocketChatServerURL = self._settings.get(
                    ["rocketchat_config"], merged=True
                ).get("server_url")
                rocketChatUsername = self._settings.get(
                    ["rocketchat_config"], merged=True
                ).get("username")
                rocketChatPassword = self._settings.get(
                    ["rocketchat_config"], merged=True
                ).get("password")
                if not rocketChatServerURL == None:
                    rocketChatServerURL = rocketChatServerURL.strip()
                if not rocketChatUsername == None:
                    rocketChatUsername = rocketChatUsername.strip()
                if not rocketChatPassword == None:
                    rocketChatPassword = rocketChatPassword.strip()

                if (
                    rocketChatServerURL == None
                    or len(rocketChatServerURL) == 0
                    or rocketChatUsername == None
                    or len(rocketChatUsername) == 0
                    or rocketChatPassword == None
                    or len(rocketChatPassword) == 0
                ):
                    self._logger.error(
                        "Rocket.Chat connection not available, skipping message send"
                    )
                    return
                    return
            elif connection_method == "MATRIX":
                matrixServerURL = self._settings.get(
                    ["matrix_config"], merged=True
                ).get("server_url")
                matrixAccessToken = self._settings.get(
                    ["matrix_config"], merged=True
                ).get("access_token")
                matrixUserID = self._settings.get(["matrix_config"], merged=True).get(
                    "user_id"
                )
                if not matrixServerURL == None:
                    matrixServerURL = matrixServerURL.strip()
                if not matrixAccessToken == None:
                    matrixAccessToken = matrixAccessToken.strip()
                if not matrixUserID == None:
                    matrixUserID = matrixUserID.strip()

                if (
                    matrixServerURL == None
                    or len(matrixServerURL) == 0
                    or matrixAccessToken == None
                    or len(matrixAccessToken) == 0
                    or matrixUserID == None
                    or len(matrixUserID) == 0
                ):
                    self._logger.error(
                        "Matrix connection not available, skipping message send"
                    )

            attachments = [{}]
            attachment = attachments[0]

            attachment["mrkdwn_in"] = ["text", "pretext"]

            hosted_url = None
            snapshot_upload_method = self._settings.get(
                ["snapshot_upload_method"], merged=True
            )
            snapshot_url_to_append = None
            snapshot_msg = None

            snapshot_error_msgs = None

            if includeSnapshot:
                hosted_url, error_msgs, slack_rsp = self.upload_snapshot()
                snapshot_error_msgs = error_msgs

                if hosted_url:
                    if snapshot_upload_method == "SLACK":
                        if slackAPIToken:
                            now = time.time()

                            if event == "Progress" and (
                                self._slack_next_progress_snapshot_time > 0
                                and now < self._slack_next_progress_snapshot_time
                            ):
                                snapshot_msg = None
                            else:
                                if event == "Progress":
                                    self._slack_next_progress_snapshot_time = (
                                        now + slack_progress_snapshot_min_interval
                                    )

                                desc = event + " snapshot"
                                if (
                                    event == "Progress"
                                    and print_pct_complete
                                    and print_pct_complete != "N/A"
                                ):
                                    desc = desc + " taken @ " + print_pct_complete

                                snapshot_msg = {
                                    "local_file": hosted_url,
                                    "filename": "snapshot.jpg",
                                    "description": desc,
                                }
                        else:
                            if snapshot_error_msgs == None:
                                snapshot_error_msgs = []

                            self._logger.error(
                                "Slack API connection required for Slack asset uploads"
                            )
                            snapshot_error_msgs.append(
                                "Slack API connection required for Slack asset uploads"
                            )
                    else:
                        attachment["image_url"] = hosted_url
                        snapshot_url_to_append = hosted_url

                        ##No need to append the URL to the body text as Slack will expose the URL itself
                        if (
                            connection_method == "APITOKEN"
                            or (
                                connection_method == "WEBHOOK"
                                and not self.mattermost_mode()
                            )
                            or connection_method == "PUSHBULLET"
                            or connection_method == "PUSHOVER"
                            or (
                                connection_method == "ROCKETCHAT"
                                and snapshot_upload_method == "ROCKETCHAT"
                            )
                            or (
                                connection_method == "MATRIX"
                                and snapshot_upload_method == "MATRIX"
                            )
                            or connection_method == "DISCORD"
                            or connection_method == "TEAMS"
                        ):
                            snapshot_url_to_append = None

            if snapshot_error_msgs:
                if text == None:
                    text = ""
                elif len(text) > 0:
                    text += newline

                text += bold_text_start + "Snapshot error(s):" + bold_text_end
                if connection_method == "WEBHOOK" and self.mattermost_mode():
                    text += "\n* " + "\n* ".join(error_msgs)
                else:
                    for error_msg in snapshot_error_msgs:
                        if (
                            connection_method == "WEBHOOK"
                            or connection_method == "APITOKEN"
                        ):
                            text += "\n *-* "
                        elif connection_method == "PUSHOVER":
                            text += (
                                newline
                                + " "
                                + bold_text_start
                                + " - "
                                + bold_text_end
                                + " "
                            )
                        else:
                            text += newline + " - "

                        text += error_msg

            if (
                capture_command_returncode or capture_command_output
            ) and command_thread:
                try:
                    cmd_return_code = None
                    cmd_output = None
                    cmd_error_msg = None

                    command_thread.join(COMMAND_EXECUTION_WAIT)  ##seconds

                    if command_thread.isAlive():
                        cmd_error_msg = (
                            "Command did not return within "
                            + str(COMMAND_EXECUTION_WAIT)
                            + " seconds"
                        )
                    else:
                        cmd_return_code = command_thread_rsp.get()
                        cmd_output = command_thread_rsp.get()
                        cmd_error_msg = command_thread_rsp.get()

                    if capture_command_returncode and cmd_return_code:
                        if text == None:
                            text = ""
                        elif len(text) > 0:
                            text += newline

                        text += (
                            bold_text_start
                            + "Command return code"
                            + bold_text_end
                            + name_val_sep
                            + str(cmd_return_code)
                        )

                    if capture_command_output and cmd_output:
                        if text == None:
                            text = ""
                        elif len(text) > 0:
                            text += newline

                        text += (
                            bold_text_start
                            + "Command output"
                            + bold_text_end
                            + name_val_sep
                            + str(cmd_output)
                        )

                    if cmd_error_msg and len(cmd_error_msg.strip()) > 0:
                        if text == None:
                            text = ""
                        elif len(text) > 0:
                            text += newline

                        text += (
                            bold_text_start
                            + "Command execution error"
                            + bold_text_end
                            + name_val_sep
                            + str(cmd_error_msg.strip())
                        )
                except Exception as e:
                    self._logger.exception(
                        "An error occurred while waiting for the command thread to return or while retrieving the command output: "
                        + str(e)
                    )

                    if text == None:
                        text = ""
                    elif len(text) > 0:
                        text += newline

                    text += (
                        bold_text_start
                        + "Command execution error"
                        + bold_text_end
                        + name_val_sep
                        + str(e.message)
                    )

            if (
                connection_method == "WEBHOOK"
                and self.mattermost_mode()
                and not footer == None
                and len(footer) > 0
            ):
                if text == None:
                    text = ""
                elif len(text) > 0:
                    text += newline

                text += "`" + footer + "`"
                footer = None
            elif not footer == None and len(footer) > 0:
                attachment["footer"] = footer

            if not snapshot_url_to_append == None:
                if text == None:
                    text = ""
                elif len(text) > 0:
                    text += newline

                text += hosted_url

            if not fields == None:
                attachment["fields"] = fields

            if not fallback == None and len(fallback) > 0:
                attachment["fallback"] = fallback

            if not pretext == None and len(pretext) > 0:
                if connection_method == "WEBHOOK" and self.mattermost_mode():
                    pretext = "##### " + pretext + " #####"
                attachment["pretext"] = pretext

            if not title == None and len(title) > 0:
                attachment["title"] = title

            if not color == None and len(color) > 0:
                attachment["color"] = color

            channels = channel_override
            if channels == None or len(channels.strip()) == 0:
                if connection_method == "WEBHOOK" or connection_method == "APITOKEN":
                    channels = self._settings.get(["channel"], merged=True)
                elif connection_method == "PUSHBULLET":
                    channels = self._settings.get(
                        ["pushbullet_config"], merged=True
                    ).get("channel")
                elif connection_method == "PUSHOVER":
                    channels = "$myself$"
                elif connection_method == "ROCKETCHAT":
                    channels = self._settings.get(
                        ["rocketchat_config"], merged=True
                    ).get("channel")
                elif connection_method == "MATRIX":
                    channels = self._settings.get(["matrix_config"], merged=True).get(
                        "channel"
                    )
                elif connection_method == "DISCORD":
                    channels = self._settings.get(["discord_config"], merged=True).get(
                        "webhook_urls"
                    )
                elif connection_method == "TEAMS":
                    channels = self._settings.get(["teams_config"], merged=True).get(
                        "webhook_urls"
                    )

            if not channels:
                channels = ""

            if event == "MovieDone":
                upload_timelapse = (
                    self._settings.get(["supported_events"], merged=True)
                    .get("MovieDone")
                    .get("UploadMovie")
                )

                if upload_timelapse == True:
                    timelapse_url, timelapse_errors = self.upload_timelapse_movie(
                        event_payload["movie"], channels
                    )
                    upload_timelapse_link = (
                        self._settings.get(["supported_events"], merged=True)
                        .get("MovieDone")
                        .get("UploadMovieLink")
                    )

                    if timelapse_url and upload_timelapse_link:
                        if text == None:
                            text = ""
                        elif len(text) > 0:
                            text += newline
                        text += (
                            bold_text_start + "Timelapse" + bold_text_end + name_val_sep
                        )
                        if connection_method == "TEAMS":
                            text += "[" + timelapse_url + "](" + timelapse_url + ")"
                        else:
                            text += timelapse_url

                    if timelapse_errors:
                        if text == None:
                            text = ""
                        elif len(text) > 0:
                            text += newline

                        text += bold_text_start + "Timelapse error(s):" + bold_text_end
                        if connection_method == "WEBHOOK" and self.mattermost_mode():
                            text += "\n* " + "\n* ".join(timelapse_errors)
                        else:
                            for timelapse_error in timelapse_errors:
                                if (
                                    connection_method == "WEBHOOK"
                                    or connection_method == "APITOKEN"
                                ):
                                    text += "\n *-* "
                                elif connection_method == "PUSHOVER":
                                    text += (
                                        newline
                                        + " "
                                        + bold_text_start
                                        + " - "
                                        + bold_text_end
                                        + " "
                                    )
                                else:
                                    text += newline + " - "
                                text += timelapse_error

            if not text == None and len(text) > 0:
                attachment["text"] = text

            ##Generate message JSON
            attachments_json = json.dumps(attachments)

            self._logger.debug(
                "postMessage - Channels: " + channels + ", JSON: " + attachments_json
            )

            slack_identity_config = self._settings.get(["slack_identity"], merged=True)
            slack_as_user = slack_identity_config["existing_user"]
            slack_icon_url = None
            slack_icon_emoji = None
            slack_username = None

            if not slack_as_user:
                if (
                    "icon_url" in slack_identity_config
                    and len(slack_identity_config["icon_url"].strip()) > 0
                ):
                    slack_icon_url = slack_identity_config["icon_url"].strip()
                if (
                    not self.mattermost_mode()
                    and "icon_emoji" in slack_identity_config
                    and len(slack_identity_config["icon_emoji"].strip()) > 0
                ):
                    slack_icon_emoji = slack_identity_config["icon_emoji"].strip()
                if (
                    "username" in slack_identity_config
                    and len(slack_identity_config["username"].strip()) > 0
                ):
                    slack_username = slack_identity_config["username"].strip()

            allow_empty_channel = connection_method == "WEBHOOK"

            if len(channels) == 0:
                self._logger.debug("No channels configured")

            self._logger.debug(
                "postMessage - username="
                + str(slack_username)
                + ", as_user="
                + str(slack_as_user)
                + ", icon_url="
                + str(slack_icon_url)
                + ", icon_emoji="
                + str(slack_icon_emoji)
            )

            for channel in channels.split(","):
                channel = channel.strip()

                if len(channel) == 0 and not allow_empty_channel:
                    continue

                allow_empty_channel = False

                if not slackAPIToken == None and len(slackAPIToken) > 0:
                    try:
                        slackAPIConnection = Slacker(
                            slackAPIToken, timeout=SLACKER_TIMEOUT
                        )

                        ##Applies to both standard Progress events as well as '@bot status' Slack RTM commands
                        if event == "Progress":
                            if (
                                self._bot_progress_last_req
                                and progress_update_method == "INPLACE"
                                and connection_method == "APITOKEN"
                            ):
                                apiRsp = slackAPIConnection.chat.update(
                                    self._bot_progress_last_req.body["channel"],
                                    ts=self._bot_progress_last_req.body["ts"],
                                    text="",
                                    attachments=attachments_json,
                                )
                            else:
                                apiRsp = slackAPIConnection.chat.post_message(
                                    channel,
                                    text="",
                                    username=slack_username,
                                    as_user=slack_as_user,
                                    attachments=attachments_json,
                                    icon_url=slack_icon_url,
                                    icon_emoji=slack_icon_emoji,
                                )
                                self._bot_progress_last_req = apiRsp
                        else:
                            apiRsp = slackAPIConnection.chat.post_message(
                                channel,
                                text="",
                                username=slack_username,
                                as_user=slack_as_user,
                                attachments=attachments_json,
                                icon_url=slack_icon_url,
                                icon_emoji=slack_icon_emoji,
                            )
                        self._logger.debug(
                            "Slack API message send response: " + apiRsp.raw
                        )
                        if snapshot_msg:
                            ##TODO Doing the upload here makes it difficult to append any error messages to the slack message.
                            ##consider doing the upload first
                            hosted_url, error_msgs, slack_resp = self.upload_slack_asset(
                                snapshot_msg["local_file"],
                                snapshot_msg["filename"],
                                snapshot_msg["description"],
                                channel,
                                None,
                            )

                            if snapshot_msg.get("local_file"):
                                try:
                                    self._logger.debug(
                                        "Deleting local Slack asset: "
                                        + str(snapshot_msg["local_file"])
                                    )
                                    self.delete_file(snapshot_msg["local_file"])
                                except Exception as e:
                                    self._logger.error(
                                        "Deletion of local Slack asset failed. Local path: {}, Error: {}".format(
                                            snapshot_msg["local_file"], e
                                        )
                                    )

                            if event == "Progress":
                                # bump out the 'next time' again as an upload can take some time
                                _slack_next_progress_snapshot_time = (
                                    time.time() + slack_progress_snapshot_min_interval
                                )
                                if (
                                    progress_update_method == "INPLACE"
                                    and connection_method == "APITOKEN"
                                    and self._bot_progress_last_snapshot_queue.qsize()
                                    > 0
                                ):
                                    while (
                                        not self._bot_progress_last_snapshot_queue.empty()
                                    ):
                                        prev_snapshot = (
                                            self._bot_progress_last_snapshot_queue.get()
                                        )

                                        if prev_snapshot == None:
                                            break

                                        fid = None
                                        try:
                                            fid = prev_snapshot.body["file"]["id"]
                                            self._logger.debug(
                                                "Deleting Slack snapshot: " + str(fid)
                                            )
                                            slackAPIConnection.files.delete(fid)
                                        except Exception as e:
                                            self._logger.error(
                                                "Slack snapshot deletion error. Slack FileID: {}, Error: {}".format(
                                                    str(fid), e
                                                )
                                            )

                                self._bot_progress_last_snapshot_queue.put(slack_resp)
                    except Exception as e:
                        self._logger.exception(
                            "Slack API message send error: " + str(e)
                        )
                elif not slackWebHookUrl == None and len(slackWebHookUrl) > 0:
                    slack_msg = {}
                    slack_msg["channel"] = channel

                    if not slack_as_user == None:
                        slack_msg["as_user"] = slack_as_user
                    if not slack_icon_url == None and len(slack_icon_url.strip()) > 0:
                        slack_msg["icon_url"] = slack_icon_url.strip()
                    if (
                        not slack_icon_emoji == None
                        and len(slack_icon_emoji.strip()) > 0
                    ):
                        slack_msg["icon_emoji"] = slack_icon_emoji.strip()
                    if not slack_username == None and len(slack_username.strip()) > 0:
                        slack_msg["username"] = slack_username.strip()

                    slack_msg["attachments"] = attachments
                    self._logger.debug(
                        "Slack WebHook postMessage json: " + json.dumps(slack_msg)
                    )

                    try:
                        webHook = IncomingWebhook(slackWebHookUrl)
                        webHookRsp = webHook.post(slack_msg)
                        self._logger.debug(
                            "Slack WebHook postMessage response: " + webHookRsp.text
                        )

                        if not webHookRsp.ok:
                            self._logger.error(
                                "Slack WebHook message send failed: " + webHookRsp.text
                            )
                    except Exception as e:
                        self._logger.exception(
                            "Slack WebHook message send error: " + str(e)
                        )
                elif (
                    not pushbulletAccessToken == None and len(pushbulletAccessToken) > 0
                ):
                    self._logger.debug("Send Pushbullet msg start")
                    pb = Pushbullet(pushbulletAccessToken)

                    pb_title = None
                    pb_body = None

                    if not pretext == None and len(pretext) > 0:
                        pb_title = pretext

                    if not text == None and len(text) > 0:
                        pb_body = text

                    if not footer == None and len(footer) > 0:
                        if pb_body == None:
                            pb_body = ""
                        elif len(text) > 0:
                            pb_body += newline

                        pb_body += footer

                    if pb_title == None:
                        pb_title = ""
                    if pb_body == None:
                        pb_body = ""

                    self._logger.debug("Pushbullet msg title: " + pb_title)
                    self._logger.debug("Pushbullet msg body: " + pb_body)

                    channel_obj = None
                    if channel and not channel.lower() == "$myself$":
                        try:
                            channel_obj = pb.get_channel(channel)
                        except Exception as e:
                            self._logger.exception(
                                "Failed to retrieve Pushbullet channel ("
                                + channel
                                + ") information: "
                                + str(e)
                            )
                            continue

                    if hosted_url and len(hosted_url) > 0:
                        ##def push_file(self, file_name, file_url, file_type, body=None, title=None, device=None, chat=None, email=None, channel=None):

                        pb_filename = hosted_url[hosted_url.rfind("/") + 1 :]
                        self._logger.debug(
                            "Pushbullet msg image details: file_name: "
                            + pb_filename
                            + ", file_url="
                            + hosted_url
                        )

                        self._logger.debug("Executing Pushbullet push file")
                        ##Pushbullet seems to universally accept any image file_type (e.g. for png or jpg) but something is required to render correctly
                        push_rsp = pb.push_file(
                            file_name=pb_filename,
                            file_url=hosted_url,
                            file_type="image/png",
                            title=pb_title,
                            body=pb_body,
                            channel=channel_obj,
                        )
                    else:
                        ##def push_note(self, title, body, device=None, chat=None, email=None, channel=None):

                        self._logger.debug("Executing Pushbullet push note")
                        push_rsp = pb.push_note(
                            title=pb_title, body=pb_body, channel=channel_obj
                        )

                    self._logger.debug(
                        "Pushbullet push response: " + json.dumps(push_rsp)
                    )
                elif not pushoverAppToken == None and len(pushoverAppToken) > 0:
                    self._logger.debug("Send Pushover msg start")

                    pushoverUserKey = self._settings.get(
                        ["pushover_config"], merged=True
                    ).get("user_key")
                    if not pushoverUserKey == None:
                        pushoverUserKey = pushoverUserKey.strip()
                    if pushoverUserKey == None or len(pushoverUserKey) == 0:
                        self._logger.error(
                            "Pushover User Key not available, skipping message send"
                        )
                        return

                    po_title = None
                    po_body = None
                    pb_image_url = None
                    pb_image_title = None
                    pb_image_local_path = None

                    if not pretext == None and len(pretext) > 0:
                        po_title = pretext

                    if not text == None and len(text) > 0:
                        po_body = text

                    if not footer == None and len(footer) > 0:
                        if po_body == None:
                            po_body = ""
                        elif len(text) > 0:
                            po_body += newline

                        po_body += footer

                    if po_title == None:
                        po_title = ""
                    if po_body == None:
                        po_body = ""

                    if hosted_url and len(hosted_url) > 0:
                        if snapshot_upload_method == "PUSHOVER":
                            ##is a local file path
                            pb_image_local_path = hosted_url
                        else:
                            pb_image_url = hosted_url
                            pb_image_title = hosted_url[hosted_url.rfind("/") + 1 :]

                    po_sound = event_settings["PushoverSound"]
                    if po_sound:
                        po_sound = po_sound.strip()
                        if len(po_sound) == 0:
                            po_sound = None

                    po_priority = event_settings["PushoverPriority"]
                    if po_priority:
                        po_priority = po_priority.strip()
                        if len(po_priority) == 0:
                            po_priorirty = None

                    po_expire = None
                    po_retry = None

                    if po_priority == "2":
                        po_expire = 60
                        po_retry = 30

                    self._logger.debug("Pushover msg title: " + po_title)
                    self._logger.debug("Pushover msg body: " + po_body)
                    self._logger.debug("Pushover msg sound: " + str(po_sound))
                    self._logger.debug("Pushover msg priority: " + str(po_priority))
                    self._logger.debug("Pushover msg expire: " + str(po_expire))
                    self._logger.debug("Pushover msg retry: " + str(po_retry))

                    try:
                        po = PushoverAPI(pushoverAppToken)

                        ##send_message(user, message, device=None, title=None, url=None, url_title=None, image=None, priority=None, retry=None, expire=None, callback_url=None, timestamp=None, sound=None, html=False)
                        po_rsp = po.send_message(
                            user=pushoverUserKey,
                            title=po_title,
                            message=po_body,
                            url=pb_image_url,
                            url_title=pb_image_title,
                            image=pb_image_local_path,
                            priority=po_priority,
                            retry=po_retry,
                            expire=po_expire,
                            sound=po_sound,
                            html=1,
                        )

                        self._logger.debug(
                            "Pushover push response: " + json.dumps(po_rsp)
                        )
                    except Exception as e:
                        self._logger.exception("Pushover send error: " + str(e))

                    if pb_image_local_path:
                        self._logger.debug(
                            "Deleting local Pushover asset: " + str(pb_image_local_path)
                        )
                        self.delete_file(pb_image_local_path)
                elif (
                    not rocketChatServerURL == None
                    and len(rocketChatServerURL) > 0
                    and not rocketChatUsername == None
                    and len(rocketChatUsername) > 0
                    and not rocketChatPassword == None
                    and len(rocketChatPassword) > 0
                ):
                    self._logger.debug("Send Rocket.Chat msg start")

                    ##api = RocketChatAPI(settings={'username': 'someuser', 'password': 'somepassword',
                    ##          'domain': 'https://myrockethchatdomain.com'})

                    rc = RocketChatAPI(
                        settings={
                            "username": rocketChatUsername,
                            "password": rocketChatPassword,
                            "domain": rocketChatServerURL,
                        }
                    )

                    cc_msg = ""
                    rc_image_local_path = None

                    if hosted_url and len(hosted_url) > 0:
                        if snapshot_upload_method == "ROCKETCHAT":
                            # is a local file path
                            rc_image_local_path = hosted_url

                    if not pretext == None and len(pretext) > 0:
                        rc_msg = "_*" + pretext + "*_"

                    if not text == None and len(text) > 0:
                        if len(rc_msg) > 0:
                            rc_msg = rc_msg + "\n"
                        rc_msg = rc_msg + text

                    if not footer == None and len(footer) > 0:
                        if len(rc_msg) > 0:
                            rc_msg = rc_msg + "\n"
                        rc_msg = rc_msg + footer

                    self._logger.debug(
                        "Rocket.Chat local image path: " + str(rc_image_local_path)
                    )
                    self._logger.debug("Rocket.Chat msg: " + rc_msg)

                    try:
                        ##def send_message(self, message, room_id, **kwargs):
                        ##def upload_file(self, room_id, description, file, message, mime_type='text/plain', **kwargs):

                        rc_room_id = rc.get_room_id(channel)
                        self._logger.debug(
                            "Rocket.Chat channel: "
                            + channel
                            + ", roomid: "
                            + str(rc_room_id)
                        )

                        if rc_image_local_path and len(rc_image_local_path) > 0:
                            self._logger.debug(
                                "Rocket.Chat uploading asset + sending message"
                            )
                            rc_rsp = rc.upload_file(
                                room_id=rc_room_id,
                                description=None,
                                file=rc_image_local_path,
                                message=rc_msg,
                                mime_type="image/png",
                            )
                        else:
                            self._logger.debug("Rocket.Chat sending message")
                            rc_rsp = rc.send_message(message=rc_msg, room_id=rc_room_id)

                        self._logger.debug(
                            "Rocket.Chat send message response: " + json.dumps(rc_rsp)
                        )
                    except requests.exceptions.HTTPError as he:
                        self._logger.exception(
                            "Rocket.Chat send HTTP error: " + str(he.response.text)
                        )
                    except Exception as e:
                        self._logger.exception("Rocket.Chat send error: " + str(e))

                    if rc_image_local_path:
                        self._logger.debug(
                            "Deleting local Rocket.Chat asset: "
                            + str(rc_image_local_path)
                        )
                        self.delete_file(rc_image_local_path)
                elif (
                    not matrixServerURL == None
                    and len(matrixServerURL) > 0
                    and not matrixAccessToken == None
                    and len(matrixAccessToken) > 0
                    and not matrixUserID == None
                    and len(matrixUserID) > 0
                ):
                    self._logger.debug("Send Matrix msg start")

                    ##https://matrix.org/docs/spec/client_server/latest#m-room-message-msgtypes

                    try:
                        ##Room def send_html(self, html, body=None, msgtype="m.text"):

                        matrix = MatrixClient(
                            base_url=matrixServerURL,
                            token=matrixAccessToken,
                            user_id=matrixUserID,
                        )
                        self._logger.debug(
                            "Matrix authenticated user_id: " + str(matrix.user_id)
                        )
                        matrix_msg = ""

                        if not pretext == None and len(pretext) > 0:
                            matrix_msg = matrix_msg + "<h3>" + pretext + "</h3>"
                            ##matrix_msg = matrix_msg + "<i><b>" + pretext + "</b><i>"

                        matrix_msg = matrix_msg + "<blockquote>"

                        if not text == None and len(text) > 0:
                            if len(matrix_msg) > 0 and not matrix_msg.endswith(
                                "<blockquote>"
                            ):
                                matrix_msg = matrix_msg + "<br/>\n"
                            matrix_msg = matrix_msg + text

                        if not footer == None and len(footer) > 0:
                            if len(matrix_msg) > 0 and not matrix_msg.endswith(
                                "<blockquote>"
                            ):
                                matrix_msg = matrix_msg + "<br/>\n"
                            matrix_msg = matrix_msg + footer

                        mxc_url = None

                        if (
                            hosted_url
                            and len(hosted_url) > 0
                            and snapshot_upload_method == "MATRIX"
                        ):
                            if len(matrix_msg) > 0 and not matrix_msg.endswith(
                                "<blockquote>"
                            ):
                                matrix_msg = matrix_msg + "<br/>\n"

                            matrix_msg = matrix_msg + "<img src='" + hosted_url + "'>"

                        if len(matrix_msg) > 0:
                            matrix_msg = matrix_msg + "<br/>\n"

                        matrix_msg = matrix_msg + "</blockquote><br/>"

                        self._logger.debug("Matrix msg: " + matrix_msg)

                        matrix_room = MatrixRoom(matrix, channel)
                        matrix_rsp = matrix_room.send_html(html=matrix_msg)

                        self._logger.debug(
                            "Matrix send message response: " + json.dumps(matrix_rsp)
                        )
                    except Exception as e:
                        self._logger.exception("Matrix send error: " + str(e))
                elif (
                    connection_method == "DISCORD"
                    and (not channel == None)
                    and len(channel) > 0
                ):
                    try:
                        discordWebHookUrl = channel
                        self._logger.debug(
                            "Discord msg channel WebHook: " + str(discordWebHookUrl)
                        )

                        discord_color = None
                        if color == "good":
                            discord_color = 242424
                        elif color == "warning":
                            discord_color = 16758825
                        elif color == "danger":
                            discord_color = 16212835

                        alternate_username = self._settings.get(
                            ["discord_config"], merged=True
                        ).get("alternate_username")
                        if (
                            not alternate_username
                            or len(alternate_username.strip()) == 0
                        ):
                            alternate_username = None

                        avatar_url = self._settings.get(
                            ["discord_config"], merged=True
                        ).get("avatar_url")
                        if not avatar_url or len(avatar_url.strip()) == 0:
                            avatar_url = None

                        self._logger.debug(
                            "Discord msg alternate username: " + str(alternate_username)
                        )
                        self._logger.debug("Discord msg avatar url: " + str(avatar_url))
                        self._logger.debug("Discord msg color: " + str(discord_color))

                        content = "**" + pretext + "**"

                        discord = DiscordWebhook(
                            url=discordWebHookUrl,
                            username=alternate_username,
                            avatar_url=avatar_url,
                            content=content,
                        )

                        embed = DiscordEmbed(
                            title=None, description="\n" + text, color=discord_color
                        )

                        if hosted_url and len(hosted_url) > 0:
                            if snapshot_upload_method == "DISCORD":
                                self._logger.debug(
                                    "Discord snapshot image to attach: "
                                    + str(hosted_url)
                                )
                                snapshot_filename = hosted_url[
                                    hosted_url.rfind("/") + 1 :
                                ]
                                with open(hosted_url, "rb") as f:
                                    discord.add_file(
                                        file=f.read(), filename=snapshot_filename
                                    )
                            else:
                                embed.set_image(url=hosted_url)

                        if (
                            event == "MovieDone"
                            and "movie" in event_payload
                            and snapshot_upload_method == "DISCORD"
                        ):
                            timelapse_movie = event_payload["movie"]
                            self._logger.debug(
                                "Discord timelapse movie to attach: "
                                + str(timelapse_movie)
                            )
                            movie_filename = timelapse_movie[
                                timelapse_movie.rfind("/") + 1 :
                            ]
                            with open(timelapse_movie, "rb") as f:
                                discord.add_file(file=f.read(), filename=movie_filename)

                        if not footer == None and len(footer) > 0:
                            embed.set_footer(text=footer)

                        discord.add_embed(embed)

                        self._logger.debug(
                            "Discord WebHook message json: " + json.dumps(discord.json)
                        )

                        discordRsp = discord.execute()

                        self._logger.debug(
                            "Discord WebHook execute response: "
                            + "\n    Status Code: "
                            + str(discordRsp.status_code)
                            + "\n    Headers: \n"
                            + str(discordRsp.headers)
                            + "\n    Content: \n"
                            + str(discordRsp.content)
                        )
                    except Exception as e:
                        self._logger.exception(
                            "Discord WebHook message send error: " + str(e)
                        )
                elif (
                    connection_method == "TEAMS"
                    and (not channel == None)
                    and len(channel) > 0
                ):
                    try:
                        teamsWebHookUrl = channel
                        self._logger.debug(
                            "Teams msg channel WebHook: " + str(teamsWebHookUrl)
                        )

                        msg_color = None
                        if color == "good":
                            msg_color = "03B2F8"
                        elif color == "warning":
                            msg_color = "FFB829"
                        elif color == "danger":
                            msg_color = "F76363"

                        msg_text = ""

                        if not text == None and len(text) > 0:
                            if len(msg_text) > 0:
                                msg_text = msg_text + "\n\n"
                            msg_text = msg_text + text

                        teams_msg = pymsteams.connectorcard(teamsWebHookUrl)
                        if pretext:
                            teams_msg.title(pretext)
                        if msg_color:
                            teams_msg.color(msg_color)
                        if msg_text:
                            teams_msg.text(msg_text)
                        if not fallback == None and len(fallback) > 0:
                            teams_msg.summary(fallback)

                        if (hosted_url and len(hosted_url) > 0) or (
                            not footer == None and len(footer) > 0
                        ):
                            if hosted_url and len(hosted_url) > 0:
                                msg_section = pymsteams.cardsection()
                                msg_section.addImage(hosted_url)
                                teams_msg.addSection(msg_section)

                            msg_section = pymsteams.cardsection()
                            if hosted_url and len(hosted_url) > 0:
                                msg_section.activitySubtitle(
                                    "[" + hosted_url + "](" + hosted_url + ")"
                                )
                            if not footer == None and len(footer) > 0:
                                msg_section.activityText(footer)

                            teams_msg.addSection(msg_section)

                        self._logger.debug(
                            "Teams WebHook message json: "
                            + json.dumps(teams_msg.payload)
                        )

                        teamsRsp = teams_msg.send()

                        self._logger.debug(
                            "Teams WebHook execute response: " + str(teamsRsp)
                        )
                    except Exception as e:
                        self._logger.exception(
                            "Teams WebHook message send error: " + str(e)
                        )
        except Exception as e:
            self._logger.exception("Send message error: " + str(e))

    tmp_imgur_client = None

    def upload_snapshot(self):
        snapshot_upload_method = self._settings.get(
            ["snapshot_upload_method"], merged=True
        )
        self._logger.debug(
            "Upload snapshot - snapshot_upload_method: " + snapshot_upload_method
        )
        if snapshot_upload_method == None or snapshot_upload_method == "NONE":
            return None, None, None

        connection_method = self.connection_method()

        local_file_path, error_msgs = self.retrieve_snapshot_images()
        if local_file_path == None:
            return None, error_msgs, None

        dest_filename = local_file_path[local_file_path.rfind("/") + 1 :]

        self._logger.debug(
            "Upload snapshot - connection_method: "
            + str(connection_method)
            + ", snapshot_upload_method: "
            + snapshot_upload_method
        )

        # Return the file object, later logic will actually upload the asset
        if (
            (connection_method == "APITOKEN" and snapshot_upload_method == "SLACK")
            or (
                connection_method == "PUSHOVER" and snapshot_upload_method == "PUSHOVER"
            )
            or (
                connection_method == "ROCKETCHAT"
                and snapshot_upload_method == "ROCKETCHAT"
            )
            or (connection_method == "DISCORD" and snapshot_upload_method == "DISCORD")
        ):
            return local_file_path, error_msgs, None

        return self.upload_asset(local_file_path, dest_filename, None, error_msgs)

    def upload_timelapse_movie(self, local_file_path, channels):
        try:
            snapshot_upload_method = self._settings.get(
                ["snapshot_upload_method"], merged=True
            )
            if snapshot_upload_method == None or snapshot_upload_method == "NONE":
                return None, None

            if (
                snapshot_upload_method == "PUSHOVER"
                or snapshot_upload_method == "ROCKETCHAT"
                or snapshot_upload_method == "MATRIX"
                or snapshot_upload_method == "DISCORD"
            ):
                return None, None

            error_msgs = []

            if snapshot_upload_method == "IMGUR":
                # Imgur does not currently support video uploads
                self._logger.exception(
                    "Timelapse upload error: Imgur does not currently support video uploads"
                )
                error_msgs.append("Imgur does not currently support video uploads")
                return None, error_msgs

            wait_start = time.time()
            while not os.path.exists(local_file_path):
                if time.time() - wait_start > 15:
                    self._logger.exception(
                        "Timelapse upload error: Unable to locate timelapse on disk"
                    )
                    error_msgs.append("Unable to locate timelapse on disk")
                    return None, error_msgs

                time.sleep(5)

            file_path, file_name = os.path.split(local_file_path)
            dest_filename = file_name

            url, error_msgs, slack_rsp = self.upload_asset(
                local_file_path, dest_filename, channels, error_msgs
            )

            self._logger.debug(
                "Upload timelapse ret: URL: "
                + str(url)
                + ", ErrorMsgs: "
                + str(error_msgs)
            )
            return url, error_msgs
        except Exception as e:
            self._logger.exception("Snapshot upload error: " + str(e))
            error_msgs.append(str(e))
            return None, error_msgs

    ##Channels is only required/used for Slack uploads
    def upload_asset(self, local_file_path, dest_filename, channels, error_msgs):
        snapshot_upload_method = self._settings.get(
            ["snapshot_upload_method"], merged=True
        )
        if snapshot_upload_method == None or snapshot_upload_method == "NONE":
            return None, error_msgs, None

        connection_method = self.connection_method()

        if error_msgs == None:
            error_msgs = []

        self._logger.debug(
            "Upload asset - Snapshot upload method: "
            + snapshot_upload_method
            + ", Local file path: "
            + str(local_file_path)
            + ", Destination filename: "
            + str(dest_filename)
        )

        if local_file_path:
            try:
                if snapshot_upload_method == "S3":
                    try:
                        self._logger.debug("Uploading snapshot via S3")

                        s3_upload_start = time.time()

                        s3_config = self._settings.get(["s3_config"], merged=True)

                        awsAccessKey = s3_config["AWSAccessKey"]
                        awsSecretKey = s3_config["AWSsecretKey"]
                        s3Bucket = s3_config["s3Bucket"]
                        fileExpireDays = int(s3_config["file_expire_days"])
                        s3URLStyle = s3_config["URLStyle"]

                        s3_expiration = timedelta(days=fileExpireDays)

                        imgData = open(local_file_path, "rb")

                        uploadFilename = dest_filename

                        s3conn = tinys3.Connection(awsAccessKey, awsSecretKey, tls=True)
                        s3UploadRsp = s3conn.upload(
                            uploadFilename,
                            imgData,
                            s3Bucket,
                            headers={"x-amz-acl": "public-read"},
                            expires=s3_expiration,
                        )

                        self._logger.debug("S3 upload response: " + str(s3UploadRsp))
                        s3_upload_elapsed = time.time() - s3_upload_start
                        self._logger.debug(
                            "Uploaded asset to S3 in "
                            + str(round(s3_upload_elapsed, 2))
                            + " seconds"
                        )

                        if s3URLStyle and s3URLStyle == "VIRTUAL":
                            return (
                                "https://"
                                + s3Bucket
                                + ".s3.amazonaws.com/"
                                + uploadFilename,
                                error_msgs,
                                None,
                            )
                        else:
                            return (
                                "https://s3.amazonaws.com/"
                                + s3Bucket
                                + "/"
                                + uploadFilename,
                                error_msgs,
                                None,
                            )
                    except Exception as e:
                        self._logger.exception(
                            "Failed to upload asset to S3: " + str(e)
                        )
                        error_msgs.append("S3 error: " + str(e))
                elif snapshot_upload_method == "MINIO":
                    try:
                        self._logger.debug("Uploading asset via Minio")

                        minio_upload_start = time.time()

                        minio_config = self._settings.get(["minio_config"], merged=True)

                        minioAccessKey = minio_config["AccessKey"]
                        minioSecretKey = minio_config["SecretKey"]
                        minioBucket = minio_config["Bucket"]
                        if minio_config["secure"]:
                            minioURI = "https://{endpoint}/{bucket}/".format(
                                endpoint=minio_config["Endpoint"], bucket=minioBucket
                            )
                        else:
                            minioURI = "http://{endpoint}/{bucket}/".format(
                                endpoint=minio_config["Endpoint"], bucket=minioBucket
                            )
                        uploadFilename = dest_filename

                        minioClient = Minio(
                            minio_config["Endpoint"],
                            access_key=minioAccessKey,
                            secret_key=minioSecretKey,
                            secure=minio_config["secure"],
                        )
                        minioUploadRsp = minioClient.fput_object(
                            minioBucket, uploadFilename, local_file_path
                        )

                        self._logger.debug(
                            "Minio upload response: " + str(minioUploadRsp)
                        )
                        minio_upload_elapsed = time.time() - minio_upload_start
                        self._logger.debug(
                            "Uploaded asset to Minio in "
                            + str(round(minio_upload_elapsed, 2))
                            + " seconds"
                        )

                        return minioURI + uploadFilename, error_msgs, None
                    except Exception as e:
                        self._logger.exception(
                            "Failed to upload asset to Minio: " + str(e)
                        )
                        error_msgs.append("Minio error: " + str(e))
                elif snapshot_upload_method == "IMGUR":
                    try:
                        self._logger.debug("Uploading asset via Imgur")

                        imgur_upload_start = time.time()

                        imgur_config = self._settings.get(["imgur_config"], merged=True)

                        imgur_client_id = imgur_config["client_id"]
                        imgur_client_secret = imgur_config["client_secret"]
                        imgur_client_refresh_token = imgur_config["refresh_token"]
                        imgur_album_id = imgur_config["album_id"]

                        if (
                            imgur_client_refresh_token == None
                            or len(imgur_client_refresh_token.strip()) == 0
                        ):
                            imgur_client_refresh_token = None
                        else:
                            imgur_client_refresh_token = (
                                imgur_client_refresh_token.strip()
                            )

                        if imgur_album_id == None or len(imgur_album_id.strip()) == 0:
                            imgur_album_id = None
                        else:
                            imgur_album_id = imgur_album_id.strip()

                        if (
                            imgur_client_refresh_token == None
                            or len(imgur_client_refresh_token) == 0
                        ) and (imgur_album_id and len(imgur_album_id) > 0):
                            self._logger.error(
                                "Usage of an Imgur Album ID requires a valid Refresh Token"
                            )
                            error_msgs.append(
                                "Imgur error: Use of an Album ID requires a valid Refresh Token"
                            )
                            return None, error_msgs, None

                        imgur_client = ImgurClient(
                            imgur_client_id,
                            imgur_client_secret,
                            None,
                            imgur_client_refresh_token,
                        )
                        self.tmp_imgur_client = imgur_client

                        imgur_upload_config = {}
                        if not imgur_album_id == None:
                            imgur_upload_config["album"] = imgur_album_id

                            imgur_upload_config["title"] = dest_filename
                            ##imgur_upload_config['title'] = 'ImageTitle123'
                            ##imgur_upload_config['description'] = 'ImageDescription123'

                        self._logger.debug(
                            "Uploading to Imgur - Config: "
                            + str(imgur_upload_config)
                            + ", File path: "
                            + local_file_path
                            + ", File exists: "
                            + str(os.path.isfile(local_file_path))
                        )

                        ##Required to work around Imgur servers not always properly returning a 403
                        if imgur_client.auth:
                            self._logger.debug("Executing manual Imgur auth refresh")
                            imgur_client.auth.refresh()

                        imgurUploadRsp = imgur_client.upload_from_path(
                            local_file_path, config=imgur_upload_config, anon=False
                        )

                        self._logger.debug(
                            "Imgur upload response: " + str(imgurUploadRsp)
                        )

                        imgur_upload_elapsed = time.time() - imgur_upload_start
                        self._logger.debug(
                            "Uploaded asset to Imgur in "
                            + str(round(imgur_upload_elapsed, 2))
                            + " seconds"
                        )

                        imgurUrl = imgurUploadRsp["link"]
                        return imgurUrl, error_msgs, None
                    except ImgurClientError as ie:
                        self._logger.exception(
                            "Failed to upload snapshot to Imgur (ImgurClientError): "
                            + str(ie.error_message)
                            + ", StatusCode: "
                            + str(ie.status_code)
                        )
                        if not self.tmp_imgur_client == None:
                            self._logger.exception(
                                "ImgurClient Credits: "
                                + str(self.tmp_imgur_client.credits)
                            )
                        error_msgs.append("Imgur error: " + str(ie.error_message))
                        error_msgs.append(
                            "Imgur credits: " + str(self.tmp_imgur_client.credits)
                        )
                    except ImgurClientRateLimitError as rle:
                        self._logger.exception(
                            "Failed to upload snapshot to Imgur (ImgurClientRateLimitError): "
                            + str(rle)
                        )
                        if not self.tmp_imgur_client == None:
                            self._logger.exception(
                                "ImgurClient Credits: "
                                + str(self.tmp_imgur_client.credits)
                            )
                        error_msgs.append("Imgur error: " + str(rle))
                        error_msgs.append(
                            "Imgur credits: " + str(self.tmp_imgur_client.credits)
                        )
                    except Exception as e:
                        self._logger.exception(
                            "Failed to upload snapshot to Imgur (Exception): " + str(e)
                        )
                        error_msgs.append("Imgur error: " + str(e))
                elif (
                    connection_method == "WEBHOOK" or connection_method == "APITOKEN"
                ) and snapshot_upload_method == "SLACK":
                    return self.upload_slack_asset(
                        local_file_path,
                        dest_filename,
                        dest_filename,
                        channels,
                        error_msgs,
                    )
                elif (
                    connection_method == "PUSHBULLET"
                    and snapshot_upload_method == "PUSHBULLET"
                ):
                    try:
                        self._logger.debug("Uploading asset via Pushbullet")

                        pushbullet_upload_start = time.time()

                        pushbulletAccessToken = self._settings.get(
                            ["pushbullet_config"], merged=True
                        ).get("access_token")

                        pb_rsp = None

                        if not pushbulletAccessToken == None:
                            pushbulletAccessToken = pushbulletAccessToken.strip()
                        if (
                            pushbulletAccessToken == None
                            or len(pushbulletAccessToken) == 0
                        ):
                            self._logger.error(
                                "Pushbullet connection not available, skipping asset upload"
                            )
                        else:
                            with open(local_file_path, "rb") as img_file:
                                try:
                                    pb = Pushbullet(pushbulletAccessToken)
                                    pb_rsp = pb.upload_file(img_file, dest_filename)
                                    self._logger.debug(
                                        "Pushbullet asset upload response: "
                                        + str(pb_rsp)
                                    )

                                    pushbullet_upload_elapsed = (
                                        time.time() - pushbullet_upload_start
                                    )
                                    self._logger.debug(
                                        "Uploaded asset to Pushbullet in "
                                        + str(round(pushbullet_upload_elapsed, 2))
                                        + " seconds"
                                    )
                                except Exception as e:
                                    self._logger.exception(
                                        "Error while uploading snapshot to Pushbullet, sending only a note: {}".format(
                                            str(e)
                                        )
                                    )
                                    error_msgs.append("Pushbullet error: " + str(e))

                        if pb_rsp and "file_url" in pb_rsp:
                            return pb_rsp["file_url"], error_msgs, None
                    except Exception as e:
                        self._logger.exception(
                            "Failed to upload asset to Pushbullet: " + str(e)
                        )
                        error_msgs.append("Pushbullet error: " + str(e))
                elif (
                    connection_method == "MATRIX" and snapshot_upload_method == "MATRIX"
                ):
                    try:
                        self._logger.debug("Uploading asset via Matrix")

                        matrix_upload_start = time.time()

                        matrixServerURL = self._settings.get(
                            ["matrix_config"], merged=True
                        ).get("server_url")
                        matrixAccessToken = self._settings.get(
                            ["matrix_config"], merged=True
                        ).get("access_token")
                        matrixUserID = self._settings.get(
                            ["matrix_config"], merged=True
                        ).get("user_id")

                        if not matrixServerURL == None:
                            matrixServerURL = matrixServerURL.strip()
                        if not matrixAccessToken == None:
                            matrixAccessToken = matrixAccessToken.strip()
                        if not matrixUserID == None:
                            matrixUserID = matrixUserID.strip()

                        matrix_rsp = None

                        if (
                            matrixServerURL == None
                            or len(matrixServerURL) == 0
                            or matrixAccessToken == None
                            or len(matrixAccessToken) == 0
                            or matrixUserID == None
                            or len(matrixUserID) == 0
                        ):
                            self._logger.error(
                                "Matrix connection not available, skipping asset upload"
                            )
                        else:
                            matrix = MatrixClient(
                                base_url=matrixServerURL,
                                token=matrixAccessToken,
                                user_id=matrixUserID,
                            )
                            self._logger.debug(
                                "Matrix authenticated user_id: " + str(matrix.user_id)
                            )

                            with open(local_file_path, "rb") as img_file:
                                try:
                                    img_bytes = img_file.read()
                                    matrix_rsp = matrix.upload(
                                        content=img_bytes, content_type="image/png"
                                    )
                                    self._logger.debug(
                                        "Matrix upload response: "
                                        + json.dumps(matrix_rsp)
                                    )

                                    matrix_upload_elapsed = (
                                        time.time() - matrix_upload_start
                                    )
                                    self._logger.debug(
                                        "Uploaded asset to Matrix in "
                                        + str(round(matrix_upload_elapsed, 2))
                                        + " seconds"
                                    )

                                    return matrix_rsp, error_msgs, None
                                except Exception as e:
                                    self._logger.exception(
                                        "Error while uploading snapshot to Matrix, sending only a note: {}".format(
                                            str(e)
                                        )
                                    )
                                    error_msgs.append("Matrix error: " + str(e))
                    except Exception as e:
                        self._logger.exception(
                            "Failed to upload asset to Matrix: " + str(e)
                        )
                        error_msgs.append("Matrix error: " + str(e))
            except Exception as e:
                self._logger.exception("Asset upload error: %s" % str(e))
                error_msgs.append(str(e.message))
            finally:
                if local_file_path:
                    self._logger.debug(
                        "Deleting local asset after upload: " + str(local_file_path)
                    )
                    self.delete_file(local_file_path)
                self.tmp_imgur_client = None
        return None, error_msgs, None

    def upload_slack_asset(
        self, local_file_path, dest_filename, file_description, channels, error_msgs
    ):
        if error_msgs == None:
            error_msgs = []

        connection_method = self.connection_method()
        if connection_method == None or connection_method != "APITOKEN":
            self._logger.error("Slack API connection required for Slack asset uploads")
            error_msgs.append("Slack API connection required for Slack asset uploads")
            return None, error_msgs, None

        self._logger.debug("Uploading asset via Slack")

        if channels == None or len(channels) == 0:
            self._logger.exception("Slack asset upload failed. Channels list was empty")
            error_msgs.append("Slack channels list was empty")
            return None, error_msgs, None

        slack_upload_start = time.time()

        slackAPIConnection = None

        slackAPIToken = self._settings.get(["slack_apitoken_config"], merged=True).get(
            "api_token"
        )

        if not slackAPIToken == None:
            slackAPIToken = slackAPIToken.strip()

        if slackAPIToken and len(slackAPIToken) > 0:
            slackAPIConnection = Slacker(slackAPIToken, timeout=SLACKER_TIMEOUT)

        if slackAPIConnection == None:
            self._logger.exception("Slack API connection unavailable")
            error_msgs.append("Slack API connection unavailable")
            return None, error_msgs, None

        file_size = os.stat(local_file_path).st_size

        # str() needd to works around Slacker isinsance(lcoal_file_path, str) bug
        asset_msg = {
            "file_": str(local_file_path),
            "filename": dest_filename,
            "title": file_description,
            "channels": channels,
        }

        self._logger.debug(
            "Uploading file (" + str(file_size) + ") to Slack: " + str(asset_msg)
        )
        resp = slackAPIConnection.files.upload(**asset_msg)
        self._logger.debug("Slack API upload snapshot response: " + resp.raw)

        error_msg = None

        if resp == None:
            error_msg = "Unknown"
        elif not resp.successful:
            error_msg = resp.error

        if not error_msg == None:
            self._logger.exception(
                "Slack asset upload failed. Error: " + str(error_msg)
            )
            error_msgs.append(str(error_msg))
            return None, error_msgs, None

        slack_upload_elapsed = time.time() - slack_upload_start
        self._logger.debug(
            "Uploaded asset (local_file_path: "
            + local_file_path
            + ") to Slack in "
            + str(round(slack_upload_elapsed, 2))
            + " seconds"
        )
        download_url = resp.body.get("file").get("url_private_download")
        return download_url, error_msgs, resp

    def retrieve_snapshot_images(self):
        urls = []

        localCamera = self._settings.global_get(["webcam", "snapshot"])
        localCameraFlipH = self._settings.global_get(["webcam", "flipH"])
        localCameraFlipV = self._settings.global_get(["webcam", "flipV"])
        localCameraRotate90 = self._settings.global_get(["webcam", "rotate90"])

        self._logger.debug(
            "Local camera settings - Snapshot URL:"
            + str(localCamera)
            + ", FlipH: "
            + str(localCameraFlipH)
            + ", FlipV: "
            + str(localCameraFlipV)
            + ", Rotate90: "
            + str(localCameraRotate90)
        )

        if not localCamera == None:
            urls.append(
                (localCamera, localCameraFlipH, localCameraFlipV, localCameraRotate90)
            )

        additional_snapshot_urls = self._settings.get(
            ["additional_snapshot_urls"], merged=True
        )
        if not additional_snapshot_urls == None:
            for entry in additional_snapshot_urls.split(","):
                entry = entry.strip()
                if len(entry) == 0:
                    continue

                entry = six.moves.urllib.parse.unquote(entry)

                parts = entry.split("|")
                url = parts[0].strip()
                flipH = False
                flipV = False
                rotate90 = False

                if len(parts) == 4:
                    flipH = parts[1].strip() == "true"
                    flipV = parts[2].strip() == "true"
                    rotate90 = parts[3].strip() == "true"

                if len(url) > 0:
                    urls.append((url, flipH, flipV, rotate90))

        self._logger.debug("Snapshot URLs: " + str(urls))

        threads = []
        thread_responses = []
        downloaded_images = []
        error_msgs = []
        download_start = time.time()

        idx = 0
        for url_data in urls:
            url, flip_h, flip_v, rotate_90 = url_data

            thread_responses.append((None, None))

            t = threading.Thread(
                target=self.download_image,
                args=(url, flip_h, flip_v, rotate_90, idx, thread_responses),
            )
            t.daemon = True
            threads.append(t)
            t.start()

            idx += 1

        for t in threads:
            t.join()

        download_elapsed = time.time() - download_start
        self._logger.debug(
            "Downloaded all "
            + str(len(urls))
            + " snapshots in "
            + str(round(download_elapsed, 2))
            + " seconds"
        )

        self._logger.debug("download_image thread_responses: " + str(thread_responses))

        for (downloaded_image, error_msg) in thread_responses:
            if downloaded_image == None and error_msg == None:
                continue

            if not downloaded_image == None:
                downloaded_images.append(downloaded_image)
            if not error_msg == None:
                error_msgs.append(error_msg)

                ## The single returned image will be deleted by the caller

        if len(downloaded_images) == 0:
            return None, error_msgs

        if len(downloaded_images) > 1:
            ## downloaded_images will be deleted internally by combine_images
            combined_image, error_msg = self.combine_images(downloaded_images)
            if not error_msg == None:
                error_msgs.append(error_msg)
            return self.resize_snapshot(combined_image, error_msgs)
        else:
            return self.resize_snapshot(downloaded_images[0], error_msgs)

    def resize_snapshot(self, local_file_path, error_msgs):
        connection_method = self.connection_method()
        if not connection_method == "TEAMS":
            return local_file_path, error_msgs

        temp_fd = None
        temp_filename = None
        try:
            resize_image_start = time.time()

            img = Image.open(local_file_path)
            width, height = img.size

            ##Higher than documented limits but these appear to work so we'll use them
            max_x = 1920
            max_y = 1080

            # Image already fits
            if width <= max_x and height <= max_y:
                return local_file_path, error_msgs

            x_pct = max_x / (width * 1.0)
            y_pct = max_y / (height * 1.0)

            resize_pct = min(x_pct, y_pct)

            new_x = int(width * resize_pct)
            new_y = int(height * resize_pct)

            new_size = (new_x, new_y)

            self._logger.debug(
                "Resizing snapshot image. Orig X,Y: ("
                + str(width)
                + ","
                + str(height)
                + "), New X,Y: ("
                + str(new_size[0])
                + ","
                + str(new_size[1])
                + ")"
            )

            new_img = img.resize(new_size)

            temp_fd, temp_filename = mkstemp()
            os.close(temp_fd)

            temp_filename = self.rename_snapshot_filename(temp_filename)

            self._logger.debug("Resized image temp filename: " + str(temp_filename))
            new_img.save(temp_filename, "JPEG")

            statinfo = os.stat(temp_filename)
            new_img_size = statinfo.st_size

            resize_image_elapsed = time.time() - resize_image_start
            self._logger.debug(
                "Resized image ("
                + octoprint.util.get_formatted_size(new_img_size)
                + ") in "
                + str(round(resize_image_elapsed, 2))
                + " seconds"
            )

            img.close()
            new_img.close()

            self.delete_file(local_file_path)

            return temp_filename, error_msgs
        except Exception as e:
            self._logger.exception("Error opening snapshot image: " + str(e))
            error_msgs.append(str(e))
            return local_file_path, error_msgs

        self._logger.debug(
            "Rename tmp file - Existing tmp filename: " + str(tmp_filename)
        )
        return local_file_path, error_msgs

    def generate_snapshot_filename(self):
        return "Snapshot_" + str(uuid.uuid1()).replace("-", "") + ".png"

    def rename_snapshot_filename(self, tmp_filename):
        try:
            self._logger.debug(
                "Rename tmp file - Existing tmp filename: " + str(tmp_filename)
            )

            new_filename = (
                tmp_filename[: tmp_filename.rfind("/")]
                + "/"
                + self.generate_snapshot_filename()
            )
            self._logger.debug(
                "Rename tmp file - New tmp filename: " + str(new_filename)
            )

            os.rename(tmp_filename, new_filename)

            return new_filename
        except Exception as e:
            self._logger.exception("Error renaming tmp filename: " + str(e))
            return tmp_filename

    def download_image(self, url, flip_h, flip_v, rotate_90, rsp_idx, responses):
        imgData = None
        temp_fd = None
        temp_filename = None

        try:
            download_start = time.time()

            basic_auth_user = None
            basic_auth_pwd = None

            ##If basic auth credentials were passed in via protocol://user:pwd@host:port/path, parse them out
            if "@" in url:
                first_split = url.split("@")
                host_port_path = first_split[1]

                second_split = first_split[0].split("//")
                new_url = second_split[0] + "//" + first_split[1]

                auth_split = second_split[1].split(":")
                if len(auth_split) > 0:
                    basic_auth_user = auth_split[0]
                if len(auth_split) > 1:
                    basic_auth_pwd = auth_split[1]
                else:
                    basic_auth_pwd = ""

                    ## We have credentials
                if not basic_auth_user == None:
                    url = new_url

            imgReq = six.moves.urllib.request.Request(url)

            if not basic_auth_user == None and not basic_auth_pwd == None:
                auth_header = base64.b64encode(
                    "%s:%s" % (basic_auth_user, basic_auth_pwd)
                )
                imgReq.add_header("Authorization", "Basic %s" % auth_header)

            imgRsp = six.moves.urllib.request.urlopen(imgReq, timeout=2)

            temp_fd, temp_filename = mkstemp()
            os.close(temp_fd)

            temp_filename = self.rename_snapshot_filename(temp_filename)
            self._logger.debug("Snapshot download temp filename: " + str(temp_filename))

            temp_file = open(temp_filename, "wb")
            temp_file.write(imgRsp.read())

            imgByteCount = temp_file.tell()

            temp_file.close()

            download_elapsed = time.time() - download_start
            self._logger.debug(
                "Downloaded snapshot from URL: "
                + url
                + " ("
                + octoprint.util.get_formatted_size(imgByteCount)
                + ") in "
                + str(round(download_elapsed, 2))
                + " seconds to "
                + temp_filename
            )
            self._logger.debug(
                "Transpose operations for URL: "
                + url
                + " - FlipH: "
                + str(flip_h)
                + ", FlipV: "
                + str(flip_v)
                + ", Rotate90: "
                + str(rotate_90)
            )

            if flip_h or flip_v or rotate_90:
                self._logger.debug("Opening file to transpose image for URL: " + url)
                tmp_img = Image.open(temp_filename)
                if flip_h:
                    self._logger.debug("Flipping image horizontally for URL: " + url)
                    tmp_img = tmp_img.transpose(Image.FLIP_LEFT_RIGHT)
                    self._logger.debug("Horizontally flip complete for URL: " + url)
                if flip_v:
                    self._logger.debug("Flipping image vertically for URL: " + url)
                    tmp_img = tmp_img.transpose(Image.FLIP_TOP_BOTTOM)
                    self._logger.debug("Vertical flip complete for URL: " + url)
                if rotate_90:
                    self._logger.debug("Rotating image 90 degrees for URL: " + url)
                    tmp_img = tmp_img.transpose(Image.ROTATE_90)
                    self._logger.debug("90 degree rotate complete for URL: " + url)

                self._logger.debug(
                    "Saving transposed image for URL: " + url + " to " + temp_filename
                )

                if tmp_img.mode != "RGB":
                    self._logger.debug(
                        "Converting transposed image to RGB from: " + str(tmp_img.mode)
                    )
                    tmp_img = tmp_img.convert("RGB")

                tmp_img.save(temp_filename, "JPEG")
                tmp_img.close()

            responses[rsp_idx] = (temp_filename, None)
        except Exception as e:
            self._logger.exception(
                "Error downloading snapshot - URL: " + url + ", Error: " + str(e)
            )
            responses[rsp_idx] = (None, str(e))
        finally:
            if not imgData == None:
                imgData.close()

    def combine_images(self, local_paths):
        temp_fd = None
        temp_filename = None

        try:
            generate_image_start = time.time()

            images = []
            for local_path in local_paths:
                try:
                    img = Image.open(local_path)
                    images.append(img)
                except Exception as e:
                    self._logger.exception("Error opening downloaded image: " + str(e))

            image_count = len(images)
            if images == 0:
                return None, None

            widths, heights = list(zip(*(i.size for i in images)))

            total_width = sum(widths)
            max_width = max(widths)
            total_height = sum(heights)
            max_height = max(heights)

            grid_size = 0, 0
            grid_rows = None
            grid_row_images = []
            grid_row_heights = []
            grid_col_widths = []

            arrangement = self._settings.get(["snapshot_arrangement"], merged=True)
            if arrangement == None:
                arrangement = "HORIZONTAL"

                ##Lazy grid layout (no formula) supports up to 12 images
            if arrangement == "GRID" and image_count > 12:
                arrangement = "HORIZONTAL"

            if arrangement == "VERTICAL":
                grid_size = image_count, 1
            elif arrangement == "HORIZONTAL":
                grid_size = 1, image_count
            elif arrangement == "GRID":
                ##The grid code is a mess but it was a quick and dirt solution we can rewrite later

                if image_count == 1:
                    grid_size = 1, 1
                elif image_count == 2:
                    grid_size = 2, 1
                elif image_count == 3:
                    grid_size = 2, 2
                elif image_count == 4:
                    grid_size = 2, 2
                elif image_count == 5:
                    grid_size = 3, 2
                elif image_count == 6:
                    grid_size = 3, 2
                elif image_count == 7:
                    grid_size = 3, 3
                elif image_count == 8:
                    grid_size = 3, 3
                elif image_count == 9:
                    grid_size = 3, 3
                elif image_count == 10:
                    grid_size = 4, 3
                elif image_count == 11:
                    grid_size = 4, 3
                elif image_count == 12:
                    grid_size = 4, 3
            else:
                return None, None

            row_count, col_count = grid_size

            row_idx = 0
            col_idx = 0

            for img in images:
                if len(grid_row_images) <= row_idx:
                    grid_row_images.append([])
                if len(grid_row_heights) <= row_idx:
                    grid_row_heights.append([])
                if len(grid_col_widths) <= col_idx:
                    grid_col_widths.append([])

                width, height = img.size

                grid_row_images[row_idx].append(img)
                grid_row_heights[row_idx].append(height)
                grid_col_widths[col_idx].append(width)

                col_idx += 1
                if col_idx == col_count:
                    col_idx = 0
                    row_idx += 1

            newHeight = 0
            newWidth = 0

            for row in grid_row_heights:
                newHeight += max(row)

            for row in grid_col_widths:
                newWidth += max(row)

                ##Now that we have the exact height/width, add some spacing around/between the images
            image_spacer = 10

            newWidth += image_spacer * 2  ## outer borders
            newHeight += image_spacer * 2  ## outer borders

            newWidth += (col_count - 1) * image_spacer  ##horizontal spacers
            newHeight += (row_count - 1) * image_spacer  ##vertical spacers

            new_im = Image.new("RGB", (newWidth, newHeight))

            x_offset = image_spacer
            y_offset = image_spacer

            if arrangement == "VERTICAL" or arrangement == "HORIZONTAL":
                for im in images:
                    if arrangement == "VERTICAL":
                        x_adjust = image_spacer
                        if im.size[0] != max_width:
                            x_adjust = int((max_width - im.size[0]) / 2)

                        new_im.paste(im, (x_adjust, y_offset))
                        y_offset += im.size[1]
                        y_offset += image_spacer
                    elif arrangement == "HORIZONTAL":
                        y_adjust = image_spacer
                        if im.size[1] != max_height:
                            y_adjust = int((max_height - im.size[1]) / 2)

                        new_im.paste(im, (x_offset, y_adjust))
                        x_offset += im.size[0]
                        x_offset += image_spacer
            elif arrangement == "GRID":
                row_idx = 0
                col_idx = 0

                for im in images:
                    width, height = im.size

                    row_height = max(grid_row_heights[row_idx])
                    col_width = max(grid_col_widths[col_idx])

                    x_adjust = 0
                    if width < col_width:
                        x_adjust = int((col_width - width) / 2)

                    y_adjust = 0
                    if height < row_height:
                        y_adjust = int((row_height - height) / 2)

                    new_im.paste(im, (x_offset + x_adjust, y_offset + y_adjust))

                    col_idx += 1
                    x_offset += col_width
                    x_offset += image_spacer

                    if col_idx == col_count:
                        y_offset += row_height
                        y_offset += image_spacer
                        x_offset = image_spacer

                        col_idx = 0
                        row_idx += 1

            temp_fd, temp_filename = mkstemp()
            os.close(temp_fd)

            temp_filename = self.rename_snapshot_filename(temp_filename)

            self._logger.debug("Combine image temp filename: " + str(temp_filename))
            new_im.save(temp_filename, "JPEG")
            new_im.close()

            statinfo = os.stat(temp_filename)
            new_img_size = statinfo.st_size

            generate_image_elapsed = time.time() - generate_image_start
            self._logger.debug(
                "Generated combined image ("
                + octoprint.util.get_formatted_size(new_img_size)
                + ") in "
                + str(round(generate_image_elapsed, 2))
                + " seconds"
            )

            for im in images:
                im.close()

            for tmpFile in local_paths:
                self.delete_file(tmpFile)

            return temp_filename, None
        except Exception as e:
            self._logger.exception(
                "Error generating combined snapshot image: %s" % (str(e))
            )
            return None, str(e.message)

    active_gcode_events = []
    active_gcode_received_events = []
    active_gcode_event_regexes = dict()

    def update_gcode_sent_listeners(self):
        try:
            self._logger.debug("Updating G-code listeners")

            events_str = self._settings.get(["gcode_events"], merged=True)

            new_gcode_events = []
            new_gcode_received_events = []
            new_gcode_event_regexes = dict()

            if events_str == None or len(events_str.strip()) == 0:
                tmp_gcode_events = []
            else:
                tmp_gcode_events = json.loads(events_str)

            for gcode_event in tmp_gcode_events:
                if (
                    gcode_event["Enabled"] == False
                    and gcode_event["CommandEnabled"] == False
                ) or len(gcode_event["Gcode"].strip()) == 0:
                    continue

                if (
                    "GcodeMatchType" in gcode_event
                    and gcode_event["GcodeMatchType"] == "Regex"
                ):
                    internalName = gcode_event["InternalName"]
                    regex_text = gcode_event["Gcode"]
                    if len(regex_text.strip()) == 0:
                        continue
                    try:
                        compiled_regex = re.compile(regex_text)
                        new_gcode_event_regexes[internalName] = compiled_regex
                    except Exception as e:
                        self._logger.exception(
                            "Failed to compile G-code match regular expression: "
                            + regex_text
                            + ", Error: "
                            + str(e)
                        )

                if not "GcodeType" in gcode_event or gcode_event["GcodeType"] == "sent":
                    new_gcode_events.append(gcode_event)
                else:
                    new_gcode_received_events.append(gcode_event)

            self.active_gcode_events = new_gcode_events
            self.active_gcode_received_events = new_gcode_received_events
            self.active_gcode_event_regexes = new_gcode_event_regexes

            self._logger.debug(
                "Active G-code sent events: " + json.dumps(self.active_gcode_events)
            )

            self._logger.debug(
                "Active G-code received events: "
                + json.dumps(self.active_gcode_received_events)
            )

        except Exception as e:
            self._logger.exception("Error loading gcode listener events: %s" % (str(e)))

    def sending_gcode(
        self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs
    ):
        if (
            not gcode
            or self.active_gcode_events == None
            or len(self.active_gcode_events) == 0
        ):
            return (cmd,)

        try:
            for gcode_event in self.active_gcode_events:
                trigger_gcode = gcode_event["Gcode"]
                if "GcodeMatchType" in gcode_event:
                    match_type = gcode_event["GcodeMatchType"]
                else:
                    match_type = None

                if self.evaluate_gcode_trigger(
                    cmd, gcode_event, match_type, trigger_gcode
                ):
                    notification_enabled = gcode_event["Enabled"]
                    command_enabled = gcode_event["CommandEnabled"]

                    self._logger.debug(
                        "Caught sent G-code: "
                        + self.remove_non_ascii(cmd)
                        + ", NotificationEnabled: "
                        + str(notification_enabled)
                        + ", CommandEnabled: "
                        + str(command_enabled)
                    )

                    self.handle_event(
                        "GcodeEvent", None, {"cmd": cmd}, False, False, gcode_event
                    )
        except Exception as e:
            self._logger.exception(
                "Error attempting to match sent G-code command to the configured events, G-code: "
                + gcode
                + ", Error: "
                + str(e.message)
            )

        return (cmd,)

    def received_gcode(self, comm_instance, line, *args, **kwargs):
        if (
            not line
            or self.active_gcode_received_events == None
            or len(self.active_gcode_received_events) == 0
        ):
            return line

        try:
            for gcode_event in self.active_gcode_received_events:
                trigger_gcode = gcode_event["Gcode"]
                if "GcodeMatchType" in gcode_event:
                    match_type = gcode_event["GcodeMatchType"]
                else:
                    match_type = None

                if self.evaluate_gcode_trigger(
                    line, gcode_event, match_type, trigger_gcode
                ):
                    notification_enabled = gcode_event["Enabled"]
                    command_enabled = gcode_event["CommandEnabled"]

                    self._logger.debug(
                        "Caught received G-code: "
                        + self.remove_non_ascii(line)
                        + ", NotificationEnabled: "
                        + str(notification_enabled)
                        + ", CommandEnabled: "
                        + str(command_enabled)
                    )
                    self.handle_event(
                        "GcodeEvent",
                        None,
                        {"cmd": line},
                        notification_enabled,
                        command_enabled,
                        gcode_event,
                    )
        except Exception as e:
            self._logger.exception(
                "Error attempting to match received G-code command to the configured events, G-code: "
                + line
                + ", Error: "
                + str(e.message)
            )

        return line

    def evaluate_gcode_trigger(
        self, input_gcode, gcode_event, match_type, trigger_gcode
    ):
        if input_gcode == None or trigger_gcode == None:
            return False

        if match_type == None or len(match_type) == 0:
            match_type = "StartsWith"

        input_gcode = input_gcode.strip()
        trigger_gcode = trigger_gcode.strip()

        if len(input_gcode) == 0 or len(trigger_gcode) == 0:
            return False

        if match_type == "StartsWith":
            return input_gcode.startswith(trigger_gcode)
        elif match_type == "EndsWith":
            return input_gcode.endswith(trigger_gcode)
        elif match_type == "Contains":
            return trigger_gcode in input_gcode
        elif match_type == "Regex":
            internalName = gcode_event["InternalName"]
            if not internalName in self.active_gcode_event_regexes:
                return False

            gcode_match_regex = self.active_gcode_event_regexes[internalName]
            matches = gcode_match_regex.search(input_gcode)
            if matches:
                return True
            return False

        return False

    non_ascii_regex = re.compile(r"[^\x00-\x7F]")

    def remove_non_ascii(self, input):
        return self.non_ascii_regex.sub(" ", input)


__plugin_pythoncompat__ = ">=2.7,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = OctoslackPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
        "octoprint.comm.protocol.gcode.sending": __plugin_implementation__.sending_gcode,
        "octoprint.comm.protocol.gcode.received": __plugin_implementation__.received_gcode,
    }
