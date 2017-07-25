# coding=utf-8
# encoding: utf-8
from __future__ import absolute_import
from tempfile import mkstemp
from datetime import timedelta
from slackclient import SlackClient
from slacker import Slacker,IncomingWebhook
from imgurpython import ImgurClient
from imgurpython.helpers.error import ImgurClientError,ImgurClientRateLimitError
from PIL import Image
from octoprint.util import RepeatedTimer
from websocket import WebSocketConnectionClosedException
from minio import Minio
import octoprint.util
import octoprint.plugin
import urllib2
import datetime
import base64
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
import subprocess


class OctoslackPlugin(octoprint.plugin.SettingsPlugin,
                      octoprint.plugin.AssetPlugin,
                      octoprint.plugin.StartupPlugin,
                      octoprint.plugin.ShutdownPlugin,
                      octoprint.plugin.ProgressPlugin,
                      octoprint.plugin.EventHandlerPlugin,
                      octoprint.plugin.TemplatePlugin):

	##TODO FEATURE - generate an animated gif of the print - easy enough if we can find a python ib to create the gif (images2gif is buggy & moviepy, imageio, and and visvis which rely on numpy haven't worked out as I never neven let numpy try to finish installing after 5/10 minutes on my RasPi3)
	##TODO FEATURE - add the timelapse gallery for cancelled/failed/completed as a single image
	##TODO FEATURE - Add support for Imgur image title + description
	##TODO FEATURE - Optionally upload timelapse video to youtube & send a Slack message when the upload is complete
	##TODO ENHANCEMENT - Check every N minutes if Slack RTM client has received any data. Reconnect if it hasn't
	##TODO FEATURE - Add alerts based on GCode sent from OctoPrint (e.g. M600 color change for the Marlin firmware)
	##TODO ENHANCEMENT - Remove the need to restart OctoPrint when switching between the Slack API and WebHook
	##TODO FEATURE - Define a third set of messages for each event to allow sending M117 commands to the printer

	##~~ SettingsPlugin mixin

 	def get_settings_defaults(self):
 		return {
			"connection_method" : "APITOKEN", ##APITOKEN or WEBHOOK
			"slack_apitoken_config" : {
				"api_token" : "",
				"enable_commands" : True,
				"commands_positive_reaction" : ":thumbsup:",
				"commands_negative_reaction" : ":thumbsdown:",
				"commands_processing_reaction" : ":stopwatch:",
			},
			"slack_webhook_config" : {
				"webhook_url" : "",
			},
			"slack_identity" : {
				"existing_user" : True,
				"icon_url" : "",
				"icon_emoji" : "",
				"username" : "",
			},
			"channel" : "",
			"ignore_cancel_fail_event" : True,
			"mattermost_compatability_mode" : False,
			"include_raspi_temp" : True,
			"snapshot_upload_method" : "NONE", ##NONE, S3 or IMGUR
			"imgur_config" : {
				"client_id" : "",
				"client_secret" : "",
				"refresh_token" : "",
				"album_id" : "",
			},
			"s3_config" : {
				"AWSAccessKey" : "",
				"AWSsecretKey" : "",
				"s3Bucket" : "",
				"file_expire_days" : -1,
			},
			"minio_config" : {
				"AccessKey" : "",
				"SecretKey" : "",
				"Bucket" : "",
				"Endpoint": "s3.amazonaws.com",
				"secure": True,
			},
			"additional_snapshot_urls" : "",
			"snapshot_arrangement" : "HORIZONTAL", ##HORIZTONAL or VERTICAL or GRID
			"time_format" : "HUMAN", ##FUZZY or EXACT or HUMAN
			"supported_events" : {
				##Not a real event but we'll leverage the same config structure
                    		"Help" : {
                        		"Enabled" : True,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign: Help - Supported commands :question:",
                        		"Fallback" : "",
                        		"Color" : "good",
                        		"CaptureSnapshot" : False,
					"ReportPrinterState" : True,
					"ReportJobState" : False,
					"ReportJobOrigEstimate" : False,
					"ReportJobProgress" : False,
					"ReportFinalPrintTime" : False,
					"ReportMovieStatus" : False,
					"IncludeSupportedCommands" : True,
                        	},
                    		"Startup" : {
                        		"Enabled" : False,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  Octoprint service started :chart_with_upwards_trend:",
                        		"Fallback" : "Octoprint service started",
                        		"Color" : "good",
                        		"CaptureSnapshot" : False,
					"ReportPrinterState" : True,
					"ReportJobState" : False,
					"ReportJobOrigEstimate" : False,
					"ReportJobProgress" : False,
					"ReportFinalPrintTime" : False,
					"ReportMovieStatus" : False,
                        	},
                    		"Shutdown" : {
                        		"Enabled" : False,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  Octoprint service stopped :chart_with_downwards_trend:",
                        		"Fallback" : "Octoprint service stopped",
                        		"Color" : "good",
                        		"CaptureSnapshot" : False,
					"ReportPrinterState" : True,
					"ReportJobState" : False,
					"ReportJobOrigEstimate" : False,
					"ReportJobProgress" : False,
					"ReportFinalPrintTime" : False,
					"ReportMovieStatus" : False,
                        	},
                    		"Connecting" : {
                        		"Enabled" : False,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  Connecting to printer :satellite:",
                        		"Fallback" : "Connecting to printer",
                        		"Color" : "good",
                        		"CaptureSnapshot" : False,
					"ReportPrinterState" : True,
					"ReportJobState" : False,
					"ReportJobOrigEstimate" : False,
					"ReportJobProgress" : False,
					"ReportFinalPrintTime" : False,
					"ReportMovieStatus" : False,
                        	},
                    		"Connected" : {
                        		"Enabled" : False,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  Successfully connected to printer :computer:",
                        		"Fallback" : "Successfully connected to printer",
                        		"Color" : "good",
                        		"CaptureSnapshot" : False,
					"ReportPrinterState" : True,
					"ReportJobState" : False,
					"ReportJobOrigEstimate" : False,
					"ReportJobProgress" : False,
					"ReportFinalPrintTime" : False,
					"ReportMovieStatus" : False,
                        	},
                    		"Disconnecting" : {
                        		"Enabled" : False,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  Printer disconnecting :confused:",
                        		"Fallback" : "Printer disconnecting",
                        		"Color" : "warning",
                        		"CaptureSnapshot" : False,
					"ReportPrinterState" : True,
					"ReportJobState" : False,
					"ReportJobOrigEstimate" : False,
					"ReportJobProgress" : False,
					"ReportFinalPrintTime" : False,
					"ReportMovieStatus" : False,
                        	},
                    		"Disconnected" : {
                        		"Enabled" : False,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  Printer disconnected :worried:",
                        		"Fallback" : "Printer disconnected",
                        		"Color" : "danger",
                        		"CaptureSnapshot" : False,
					"ReportPrinterState" : True,
					"ReportJobState" : False,
					"ReportJobOrigEstimate" : False,
					"ReportJobProgress" : False,
					"ReportFinalPrintTime" : False,
					"ReportMovieStatus" : False,
                        	},
                    		"Error" : {
                        		"Enabled" : True,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  Printer error :fire:",
                        		"Fallback" : "Printer error: {error}",
                        		"Color" : "danger",
                        		"CaptureSnapshot" : True,
					"ReportPrinterState" : True,
					"ReportJobState" : False,
					"ReportJobOrigEstimate" : False,
					"ReportJobProgress" : False,
					"ReportFinalPrintTime" : False,
					"ReportMovieStatus" : False,
                        	},
                    		"PrintStarted" : {
                        		"Enabled" : True,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  A new print has started :rocket:",
                        		"Fallback" : "Print started: {print_name}, Estimate: {remaining_time}",
                        		"Color" : "good",
                        		"CaptureSnapshot" : True,
					"ReportPrinterState" : True,
					"ReportJobState" : True,
					"ReportJobOrigEstimate" : True,
					"ReportJobProgress" : False,
					"ReportFinalPrintTime" : False,
					"ReportMovieStatus" : False,
                        	},
                    		"PrintFailed" : {
                        		"Enabled" : True,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  Print failed :bomb:",
                        		"Fallback" : "Print failed: {print_name}",
                        		"Color" : "danger",
                        		"CaptureSnapshot" : True,
					"ReportPrinterState" : True,
					"ReportJobState" : True,
					"ReportJobOrigEstimate" : False,
					"ReportJobProgress" : False,
					"ReportFinalPrintTime" : False,
					"ReportMovieStatus" : False,
                        	},
                    		"PrintCancelled" : {
                        		"Enabled" : True,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  Print cancelled :no_good:",
                        		"Fallback" : "Print cancelled: {print_name}",
                        		"Color" : "warning",
                        		"CaptureSnapshot" : True,
					"ReportPrinterState" : True,
					"ReportJobState" : True,
					"ReportJobOrigEstimate" : False,
					"ReportJobProgress" : False,
					"ReportFinalPrintTime" : False,
					"ReportMovieStatus" : False,
                        	},
                    		"PrintDone" : {
                        		"Enabled" : True,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  Print finished successfully :dancer:",
                        		"Fallback" : "Print finished successfully: {print_name}, Time: {elapsed_time}",
                        		"Color" : "good",
                        		"CaptureSnapshot" : True,
					"ReportPrinterState" : True,
					"ReportJobState" : True,
					"ReportJobOrigEstimate" : True,
					"ReportJobProgress" : False,
					"ReportFinalPrintTime" : True,
					"ReportMovieStatus" : False,
                        	},
				##Not a real event but we'll leverage the same config structure
                    		"Progress" : {
                        		"Enabled" : False,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign: Print progress {pct_complete} :horse_racing:",
                        		"Fallback" : "Print progress: {pct_complete} - {print_name}, Elapsed: {elapsed_time}, Remaining: {remaining_time}",
                        		"Color" : "good",
                        		"CaptureSnapshot" : True,
					"ReportPrinterState" : True,
					"ReportJobState" : True,
					"ReportJobOrigEstimate" : False,
					"ReportJobProgress" : True,
					"ReportMovieStatus" : False,
					"IntervalPct" : 25,
					"IntervalTime" : 0,
                        	},
                    		"PrintPaused" : {
                        		"Enabled" : True,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  Print paused :zzz:",
                        		"Fallback" : "Print paused: {pct_complete} - {print_name}",
                        		"Color" : "warning",
                        		"CaptureSnapshot" : True,
					"ReportPrinterState" : True,
					"ReportJobState" : True,
					"ReportJobOrigEstimate" : True,
					"ReportJobProgress" : True,
					"ReportMovieStatus" : False,
                        	},
                    		"PrintResumed" : {
                        		"Enabled" : True,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  Print resumed :runner:",
                        		"Fallback" : "Print resumed: {pct_complete} - {print_name}",
                        		"Color" : "good",
                        		"CaptureSnapshot" : True,
					"ReportPrinterState" : True,
					"ReportJobState" : True,
					"ReportJobOrigEstimate" : True,
					"ReportJobProgress" : True,
					"ReportMovieStatus" : False,
                        	},
                    		"MovieRendering" : {
                        		"Enabled" : False,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  Timelapse movie rendering :clapper:",
                        		"Fallback" : "Timelapse movie rendering: {print_name}",
                        		"Color" : "good",
                        		"CaptureSnapshot" : False,
					"ReportPrinterState" : True,
					"ReportJobState" : False,
					"ReportJobOrigEstimate" : False,
					"ReportJobProgress" : False,
					"ReportMovieStatus" : True,
                        	},
                    		"MovieDone" : {
                        		"Enabled" : False,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  Timelapse movie rendering complete :movie_camera:",
                        		"Fallback" : "Timelapse movie rendering complete: {print_name}",
                        		"Color" : "good",
                        		"CaptureSnapshot" : False,
					"ReportPrinterState" : True,
					"ReportJobState" : False,
					"ReportJobOrigEstimate" : False,
					"ReportJobProgress" : False,
					"ReportMovieStatus" : True,
                        	},
                    		"MovieFailed" : {
                        		"Enabled" : False,
                        		"ChannelOverride" : "",
                        		"Message" : ":heavy_minus_sign:  Timelapse movie rendering failed :boom:",
                        		"Fallback" : "Timelapse movie rendering failed: {print_name}, Error: {error}",
                        		"Color" : "danger",
                        		"CaptureSnapshot" : False,
					"ReportPrinterState" : True,
					"ReportJobState" : False,
					"ReportJobOrigEstimate" : False,
					"ReportJobProgress" : False,
					"ReportMovieStatus" : True,
                        	}
                    	}
		}

	def get_settings_restricted_paths(self):
		return dict(admin=[
			["slack_apitoken_config", "api_token"],
			["slack_webhook_config", "webhook_url"],
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
		])

	def get_settings_version(self):
		return 1

	def on_settings_save(self, data):
        	octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
		self.update_progress_timer()


	##~ TemplatePlugin mixin

	def get_template_vars(self):
		return dict()

	def get_template_configs(self):
		return [
			dict(type="settings", custom_bindings=False)
		]


	##~~ AssetPlugin mixin

	def get_assets(self):
		return dict(
			js=["js/Octoslack.js"],
			css=["css/Octoslack.css"],
			less=["less/Octoslack.less"]
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
				pip="https://github.com/fraschetti/Octoslack/archive/{target_version}.zip"
			)
		)

	##~~ StartupPlugin mixin

	def on_after_startup(self):
        	self._logger.debug("Starting Slack RTM client")
		self.start_rtm_client()
        	self._logger.debug("Started Slack RTM client")


	##~~ ShutdownPlugin mixin

	def on_shutdown(self):
		self.stop_rtm_client()

        	self._logger.debug("Stopped Slack RTM client")


	##~~ PrintProgress mixin

	def on_print_progress(self, location, path, progress):
		try:
			self._logger.debug("Progress: " + str(progress))

			progress_interval = int(self._settings.get(['supported_events'], merged=True).get('Progress').get('IntervalPct'))

			if (progress % progress_interval == 0 and progress != 0) or progress == 100:
				self.handle_event("Progress", None, {"progress":progress}, False)
		except Exception as e:
			self._logger.exception("Error processing progress event, Error: " + str(e.message))
		

	##~~ EventPlugin mixin

	def progress_timer_tick(self):
		self._logger.debug("Progress timer tick")
 		self.handle_event("Progress", None, {}, False)

	print_cancel_time = None
	progress_timer = None

	def start_progress_timer(self):
		progress_timer_interval = int(self._settings.get(['supported_events'], merged=True).get('Progress').get('IntervalTime'))
		if progress_timer_interval > 0 and (self._printer.is_printing() or self._printer.is_paused()) and not self._printer.is_ready():
			self._logger.debug("Starting progress timer")
			self.progress_timer = RepeatedTimer(progress_timer_interval * 60, self.progress_timer_tick, run_first=False)
			self.progress_timer.start()

	def update_progress_timer(self):
		restart = False

		new_interval = int(self._settings.get(['supported_events'], merged=True).get('Progress').get('IntervalTime'))	
		if self.progress_timer == None and new_interval > 0:
			restart = True
		else:
			existing_interval = 0
			if not self.progress_timer == None:
				existing_interval = self.progress_timer.interval

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
		

	def on_event(self, event, payload):
		self.handle_event(event, None, payload, False)

	def handle_event(self, event, channel_override, payload, override_event_enabled_check):
		try:
			if event == "PrintCancelled":
				self.stop_progress_timer()
				self.print_cancel_time = time.time()
			elif event == "PrintFailed":
				self.stop_progress_timer()

				ignore_cancel_fail_event = self._settings.get(['ignore_cancel_fail_event'], merged=True)
				##If the ignore flag is enabled and we've seen a PrintCancelled within 30s, ignore the PrintFailed event
				if ignore_cancel_fail_event and not self.print_cancel_time == None and (time.time() - self.print_cancel_time) < 30:
					self._logger.debug("Ignoring PrintFailed event within accecptable window of a PrintCancelled event")
					return
			elif event == "PrintStarted":
				self.start_progress_timer()
				self.print_cancel_time = None
			elif event == "PrintDone":
				self.stop_progress_timer()
				self.print_cancel_time = None
					

			supported_events = self._settings.get(['supported_events'], merged=True)
			if supported_events == None or not event in supported_events:
				return

			event_settings = supported_events[event];

			if event_settings == None:
				return

			event_enabled = override_event_enabled_check or event_settings['Enabled']
			if not event_enabled or event_enabled == False:
				return

			if payload == None:
				payload = {}

			self._logger.debug("Event: " + event + ", ChannelOverride: " + str(channel_override) + ", Payload: " + str(payload))

			self.process_slack_event(event, event_settings, channel_override, payload)
		except Exception as e:
			self._logger.exception("Error processing event: " + event + ", Error: " + str(e.message))
	
	def process_slack_event(self, event, event_settings, channel_override, event_payload):
		fallback = ""
		pretext = ""
		title = ""
		text = ""
		text_arr = []
		color = ""
		fields = []
		footer = ""
		includeSnapshot = False
		reportPrinterState = False
		reportJobState = False
		reportJobOrigEstimate = False
		reportJobProgress = False
		reportMovieStatus = False
		reportFinalPrintTime = False
		includeSupportedCommands = False
	
		if (channel_override == None or len(channel_override.strip()) == 0) and 'ChannelOverride' in event_settings:
			channel_override = event_settings['ChannelOverride']
		if 'Fallback' in event_settings:
			fallback = event_settings['Fallback']
		if 'Message' in event_settings:
			pretext = event_settings['Message']
		if 'Color' in event_settings:
			color = event_settings['Color']
		if 'CaptureSnapshot' in event_settings:
			includeSnapshot = event_settings['CaptureSnapshot']
		if 'ReportPrinterState' in event_settings:
			reportPrinterState = event_settings['ReportPrinterState']
		if 'ReportJobState' in event_settings:
			reportJobState = event_settings['ReportJobState']
		if 'ReportJobOrigEstimate' in event_settings:
			reportJobOrigEstimate = event_settings['ReportJobOrigEstimate']
		if 'ReportJobProgress' in event_settings:
			reportJobProgress = event_settings['ReportJobProgress']
		if 'ReportMovieStatus' in event_settings:
			reportMovieStatus = event_settings['ReportMovieStatus']
		if 'ReportFinalPrintTime' in event_settings:
			reportFinalPrintTime = event_settings['ReportFinalPrintTime']
		if 'IncludeSupportedCommands' in event_settings:
			includeSupportedCommands = event_settings['IncludeSupportedCommands']

		replacement_params = {
			"{print_name}" : "N/A",
			"{pct_complete}" : "N/A",
			"{current_z}" : "N/A",
			"{elapsed_time}" : "N/A",
			"{remaining_time}" : "N/A",
			"{error}" : "N/A",
		}

		printer_data = self._printer.get_current_data()
		printer_state = printer_data['state']
		job_state = printer_data['job']
		z_height = printer_data['currentZ']
		progress_state = printer_data['progress']

		file_name = job_state['file']['name']
		if file_name == None:
			file_name = "N/A"
		replacement_params['{print_name}'] = file_name

		z_height_str = ""
		if not z_height == None and not z_height == 'None':
			z_height_str = ", Nozzle Height: " + str(z_height) + "mm"
			
		replacement_params['{current_z}'] = z_height_str


		self._logger.debug("Printer data: " + str(printer_data))

		if reportJobState:
			print_origin = job_state['file']['origin']
			if print_origin == 'local':
				print_origin = "OctoPrint"
			elif print_origin == 'sdcard':
				print_origin = "SD Card"
			elif print_origin == None:
				print_origin = "N/A"
			
			file_bytes = job_state['file']['size']
			if file_bytes == None:
				file_bytes = 0
			file_size = octoprint.util.get_formatted_size(file_bytes)

			if file_bytes > 0:
				jobStateStr = file_name + " (" + file_size + " via " + print_origin + ")"
			else:
				jobStateStr = file_name

			text_arr.append(self.bold_text() + "File" + self.bold_text() + " " + jobStateStr)

		if reportJobOrigEstimate:
			estimatedPrintTime = None
			if 'lastPrintTime' in job_state:
				estimatedPrintTime = job_state['lastPrintTime']
			if estimatedPrintTime == None:
				estimatedPrintTime = job_state['estimatedPrintTime']
			if estimatedPrintTime == None:
				estimatedPrintTime = "N/A"
			else:
				estimatedPrintTime = self.format_duration(estimatedPrintTime)
			replacement_params['{remaining_time}'] = estimatedPrintTime

			if event == "PrintDone":
				text_arr.append(self.bold_text() + "Estimated print time" + self.bold_text() + " " + estimatedPrintTime)
			else:
				text_arr.append(self.bold_text() + "Estimated print time" + self.bold_text() + " " + estimatedPrintTime)

		if event == "Progress" and 'progress' in event_payload:
			pct_complete = event_payload['progress']
		else:
			pct_complete = progress_state['completion']
		if not pct_complete == None:
			pct_complete = str(int(pct_complete)) + "%"
		if not pct_complete == None:
			replacement_params['{pct_complete}'] = pct_complete
		
		elapsed = progress_state['printTime']
		time_left = progress_state['printTimeLeft']

		elapsed_str = self.format_duration(elapsed)
		time_left_str = self.format_duration(time_left)
		
		if not elapsed == None:
			replacement_params['{elapsed_time}'] = elapsed_str
		if not time_left == None:
			replacement_params['{remaining_time}'] = time_left_str

		if reportJobProgress and not pct_complete == None:
			text_arr.append(self.bold_text() + "Elapsed" + self.bold_text() + " " + elapsed_str)
			text_arr.append(self.bold_text() + "Remaining" + self.bold_text() + " " + time_left_str)

		##Is rendered as a footer so it's safe to always include this
		if reportPrinterState:
			printer_temps = self._printer.get_current_temperatures()
			
			temp_str = ""
			if not printer_temps == None and 'bed' in printer_temps:
				temp_str = ""
				for key in printer_temps:
					if key == 'bed':
						temp_str += ", Bed: " + str(printer_temps['bed']['actual']) + unichr(176) + "C/" + str(printer_temps['bed']['target']) + unichr(176) + "C"
					elif key.startswith('tool'):
						nozzle_name = "Nozzle"
						if len(printer_temps) > 2:
							nozzle_name += key[4:]
						
						temp_str += ", " + nozzle_name + ": " + str(printer_temps[key]['actual']) + unichr(176) + "C/" + str(printer_temps[key]['target']) + unichr(176) + "C"

			printer_text = printer_state['text']
			if not printer_text == None:
				printer_text = printer_text.strip()
			footer = "Printer: " + printer_text + temp_str + z_height_str


		if self._settings.get(['include_raspi_temp'], merged=True):

			rpi_tmp = None
			try:
				rpi_tmp = subprocess.check_output(['/opt/vc/bin/vcgencmd', 'measure_temp'])
				if not rpi_tmp == None and rpi_tmp.startswith("temp="):
					rpi_tmp = rpi_tmp.strip()
					rpi_tmp = rpi_tmp[5:-2]
				else:
					rpi_tmp = None
			except Exception as e:
				self._logger.exception("Failed to read Raspberry Pi temp - Error: " + str(e))

			if not rpi_tmp == None:
				if len(footer) > 0:
					footer += ", "

				footer += "RasPi: " + rpi_tmp +  unichr(176) + "C"


		final_time = "N/A"
		if event == "PrintDone" and 'time' in event_payload:
			final_time = self.format_duration(event_payload['time'])
			replacement_params['{elapsed_time}'] = final_time
			
		if reportFinalPrintTime:
			text_arr.append(self.bold_text() + "Final print time" + self.bold_text() + " " + final_time)

		if reportMovieStatus:
			movie_name = None
			print_filename = None

			if 'movie_basename' in event_payload:
				movie_name = event_payload['movie_basename']
			if 'gcode' in event_payload:
				print_filename = event_payload['gcode']

			if not movie_name == None:
				text_arr.append(self.bold_text() + "Movie" + self.bold_text() + " " + movie_name)
			if not print_filename == None:
				text_arr.append(self.bold_text() + "Print job" + self.bold_text() + " " + print_filename)

		if includeSupportedCommands:
			 text_arr.append(self.bold_text() + "help" + self.bold_text() + " - Displays this list of commands")
			 text_arr.append(self.bold_text() + "status" + self.bold_text() + " - Display the current print job status")
			 text_arr.append(self.bold_text() + "stop" + self.bold_text() + " - Stop the current print")
			 text_arr.append(self.bold_text() + "pause" + self.bold_text() + " - Pause the current print")
			 text_arr.append(self.bold_text() + "resume" + self.bold_text() + " - Resume a paused print")

		error = None
		if 'error' in event_payload:
			error = event_payload['error']
		if not error == None:
			error = error.strip()
		if not error == None and len(error) > 0:
			text_arr.append(self.bold_text() + "Error" + self.bold_text() + " " + error)
			replacement_params['{error}'] = error

		if not text_arr == None and len(text_arr) > 0:
			text = "\n".join(text_arr)

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

			for field in fields:
				if 'title' in field:
					field['title'] = field['title'].replace(param, replacement_params[param])
				if 'value' in field:
					field['value'] = field['value'].replace(param, replacement_params[param])
				
		self.send_slack_message(event, channel_override, fallback, pretext, title, text, color, fields, footer, includeSnapshot)


	def start_rtm_client(self):
		self.stop_rtm_client()

		if not self._settings.get(['slack_apitoken_config'], merged=True).get('enable_commands'):
			return

		connection_method = self._settings.get(['connection_method'], merged=True)
		if connection_method == None or connection_method != 'APITOKEN':
			return

		slackAPIToken = self._settings.get(['slack_apitoken_config'], merged=True).get('api_token')
		if slackAPIToken == None or len(slackAPIToken.strip()) == 0:
			self._logger.warn("Cannot enable real time messaging client for responding to commands without an API Key")
			return
		slackAPIToken = slackAPIToken.strip()

		self._logger.debug("Before Slack RTM client start")

		self.rtm_keep_running = True
		self.bot_user_id = None

		t = threading.Thread(target=self.execute_rtm_loop, args=(slackAPIToken,))
                t.setDaemon(True)
                t.start()

		self._logger.debug("After Slack RTM client start")

	def stop_rtm_client(self):
		self._logger.debug("Stopping Slack RTM client")
		self.rtm_keep_running = False

	def execute_rtm_loop(self, slackAPIToken):
		try:
			slackAPIConnection = Slacker(slackAPIToken)

			auth_rsp = slackAPIConnection.auth.test()
			self._logger.debug("API Key auth test response: " + json.dumps(auth_rsp.body))

			if auth_rsp.successful == None or auth_rsp.successful == False:
				self._logger.error("API Key auth test failed: " + json.dumps(auth_rsp.body))
				return

			self.bot_user_id = auth_rsp.body["user_id"]
			self._logger.debug("Slack RTM Bot user id: " + self.bot_user_id)

			self._logger.debug("Starting Slack RTM wait loop")
			sc = SlackClient(slackAPIToken)

			if sc.rtm_connect():
				self._logger.debug("Successfully connected via Slack RTM API")

				while self.rtm_keep_running:
					try:
						read_msgs = sc.rtm_read()
						if not read_msgs == None and len(read_msgs) > 0:
							for msg in read_msgs:
								try:
									self.process_rtm_message(slackAPIToken, msg)
								except Exception as e:
									self._logger.error("RPM message processing error: " + str(e.message))
						time.sleep(1)
					except WebSocketConnectionClosedException as ce:
						self._logger.error("RPM API read error (WebSocketConnectionClosedException): " + str(e.message))
						time.sleep(1 * 1000)

						##Reinitialize the connection
						sc = SlackClient(slackAPIToken)
						sc.rtm_connect()
						if not sc.rtm_connect():
							self._logger.error("Failed to connect via Slack RTM API")
							break
					except Exception as e:
						self._logger.error("RPM API read error (Exception): " + str(e.message))
						time.sleep(5 * 1000)
			else:
				self._logger.error("Failed to connect via Slack RTM API")

		
			self._logger.debug("Finished Slack RTM wait loop")
		except Exception as e:
			self._logger.exception("Error in rtm loop, Error: " + str(e.message))

	def process_rtm_message(self, slackAPIToken, message):
		if not self._settings.get(['slack_apitoken_config'], merged=True).get('enable_commands'):
                        return

		if self.bot_user_id == None or message == None:
			return

		if not "type" in message or message["type"] == None or message["type"] != "message" or message["text"] == None:
			return

		bot_id = "<@" + self.bot_user_id + ">"

		if not bot_id in message["text"]:
			return

		self._logger.debug("Slack RTM Read: " + json.dumps(message))

		channel = message["channel"]
		timestamp = message["ts"]

		command = message["text"].split(bot_id)[1].strip().lower()

		reaction = ""

		positive_reaction = self._settings.get(['slack_apitoken_config'], merged=True).get('commands_positive_reaction')
		negative_reaction = self._settings.get(['slack_apitoken_config'], merged=True).get('commands_negative_reaction')
		processing_reaction = self._settings.get(['slack_apitoken_config'], merged=True).get('commands_processing_reaction')

		if not positive_reaction == None:
			positive_reaction = positive_reaction.strip()
			if positive_reaction.startswith(':') and positive_reaction.endswith(':'):
				positive_reaction = positive_reaction[1:-1].strip()

		if not negative_reaction == None:
			negative_reaction = negative_reaction.strip()
			if negative_reaction.startswith(':') and negative_reaction.endswith(':'):
				negative_reaction = negative_reaction[1:-1].strip()

		if not processing_reaction == None:
			processing_reaction = processing_reaction.strip()
			if processing_reaction.startswith(':') and processing_reaction.endswith(':'):
				processing_reaction = processing_reaction[1:-1].strip()

		sent_processing_reaction = False

		if command == "help":
			self._logger.debug("Slack RTM - help command")
 			self.handle_event("Help", channel, {}, True)
			reaction = positive_reaction
			
		elif command == "stop":
			self._logger.debug("Slack RTM - stop command")
			if self._printer.is_printing():
				##Send processing reaction
				sent_processing_reaction = True
				self.add_message_reaction(slackAPIToken, channel, timestamp, processing_reaction, False)

				self._printer.cancel_print()
				reaction = positive_reaction
			else:
				reaction = negative_reaction
		elif command == "pause":
			self._logger.debug("Slack RTM - pause command")
			if self._printer.is_printing():
				##Send processing reaction
				sent_processing_reaction = True

				self.add_message_reaction(slackAPIToken, channel, timestamp, processing_reaction, False)
				self._printer.toggle_pause_print()
				reaction = positive_reaction
			else:
				reaction = negative_reaction
		elif command == "resume":
			self._logger.debug("Slack RTM - resume command")
			if self._printer.is_paused():
				##Send processing reaction
				sent_processing_reaction = True
				self.add_message_reaction(slackAPIToken, channel, timestamp, processing_reaction, False)

				self._printer.toggle_pause_print()
				reaction = positive_reaction
			else:
				reaction = negative_reaction
		elif command == "status":
			##Send processing reaction
			self._logger.debug("Slack RTM - status command")
			sent_processing_reaction = True

			self.add_message_reaction(slackAPIToken, channel, timestamp, processing_reaction, False)
 			self.handle_event("Progress", channel, {}, True)
			reaction = positive_reaction

		else:
			reaction = negative_reaction


		self.add_message_reaction(slackAPIToken, channel, timestamp, reaction, False)

		##Remove the processing reaction if it was previously added
		if sent_processing_reaction:
			self.add_message_reaction(slackAPIToken, channel, timestamp, processing_reaction, True)


	def add_message_reaction(self, slackAPIToken, channel, timestamp, reaction, remove):
		try:
			if reaction == None:
				return

			reaction = reaction.strip()

			if len(reaction) == 0:
				return

			slackAPIConnection = Slacker(slackAPIToken)
	
			self._logger.debug("Sending Slack RTM reaction - Channel: " + channel + ", Timestamp: " + timestamp + ", Reaction: " + reaction + ", Remove: " + str(remove))

			if remove:
				reaction_rsp = slackAPIConnection.reactions.remove(channel=channel, timestamp=timestamp, name=reaction)
			else:
				reaction_rsp = slackAPIConnection.reactions.add(channel=channel, timestamp=timestamp, name=reaction)

			if reaction_rsp.successful == None or reaction_rsp.successful == False:
				self._logger.debug("Slack RTM send reaction failed - Channel: " + channel + ", Timestamp: " + timestamp + ", Reaction: " + reaction + ", Remove: " + str(remove) + json.dumps(reaction_rsp.body))
			else:
				self._logger.debug("Successfully sent Slack RTM reaction - Channel: " + channel + ", Timestamp: " + timestamp + ", Reaction: " + reaction + ", Remove: " + str(remove))
		except Exception as e:
			self._logger.exception("Error sending Slack RTM reaction - Channel: " + channel + ", Timestamp: " + timestamp + ", Reaction: " + reaction + ", Remove: " + str(remove) + ", Error: " + str(e.message))

	def mattermost_mode(self):
		return self._settings.get(['mattermost_compatability_mode'], merged=True)

	def bold_text(self):
		if(self.mattermost_mode()):
			return "**"
		else:
			return "*"

	def format_duration(self, seconds):
		time_format = self._settings.get(['time_format'], merged=True)
		if seconds == None:
			return "N/A"

		delta = datetime.timedelta(seconds=seconds)

		time_format = self._settings.get(['time_format'], merged=True)
		if time_format == "FUZZY":
			return humanize.naturaldelta(delta)
		elif time_format == "EXACT":
			return octoprint.util.get_formatted_timedelta(delta)
		else:
			return self.humanize_duration(seconds)

	def humanize_duration(self, total_seconds):
		total_days = int(total_seconds / 86400)
		total_seconds -= (total_days * 86400)

		total_hours = int(total_seconds / 3600)
		total_seconds -= (total_hours * 3600)
		
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
		if len(time_str) == 0 or (total_days == 0 and total_hours == 0 and total_minutes < 10):
			if len(time_str) > 0:
				time_str += " "

			if total_seconds != 1:
				time_str += str(total_seconds) + " seconds"
			else:
				time_str += "1 second"

		return time_str


	def send_slack_message(self, event, channel_override, fallback, pretext, title, text, color, fields, footer, includeSnapshot):

		slackAPIToken = None
		slackWebHookUrl = None

		connection_method = self._settings.get(['connection_method'], merged=True)

		if connection_method == "APITOKEN":
			slackAPIToken = self._settings.get(['slack_apitoken_config'], merged=True).get('api_token')
			if not slackAPIToken == None:
				slackAPIToken = slackAPIToken.strip()
		elif connection_method == "WEBHOOK":
			slackWebHookUrl = self._settings.get(['slack_webhook_config'], merged=True).get('webhook_url')
			if not slackWebHookUrl == None:
				slackWebHookUrl = slackWebHookUrl.strip()

		if (slackAPIToken == None or len(slackAPIToken) == 0) and (slackWebHookUrl == None or len(slackWebHookUrl) == 0):
			self._logger.error("Slack connection not available, skipping message send")
			return

		attachments = [{}]
		attachment = attachments[0]

		attachment['mrkdwn_in'] = ['text', 'pretext']

		snapshot_url_to_append = None

		if includeSnapshot:
			hosted_url, snapshot_errors = self.upload_snapshot()

			if not snapshot_errors == None and len(snapshot_errors) > 0:
				if text == None:
					text = ""
				elif len(text) > 0:
					text += "\n"

				text += self.bold_text() + "Snapshot error(s):" + self.bold_text()
				if self.mattermost_mode():
					text += "\n* " + "\n* ".join(snapshot_errors)
				else:
					text += "\n"

					for snapshot_error in snapshot_errors:
						text += "\n *-* "
						text += snapshot_error

			if not hosted_url == None:
				attachment['image_url'] = hosted_url

				if self.mattermost_mode():
					snapshot_url_to_append = hosted_url

		if self.mattermost_mode() and not footer == None and len(footer) > 0:
			if text == None:
				text = ""
			elif len(text) > 0:
				text += "\n"

			text += "`" + footer + "`"
			footer = None
		elif not footer == None and len(footer) > 0:
			attachment['footer'] = footer

		if not snapshot_url_to_append == None:
			if text == None:
				text = ""
			elif len(text) > 0:
				text += "\n"

			text += hosted_url	

		if not fields == None:
			attachment['fields'] = fields

		if not fallback == None and len(fallback) > 0:
			attachment['fallback'] = fallback;

		if not pretext == None and len(pretext) > 0:
			if self.mattermost_mode():
				pretext = "##### " + pretext + " #####"
			attachment['pretext'] = pretext;

		if not title == None and len(title) > 0:
			attachment['title'] = title
		
		if not color == None and len(color) > 0:
			attachment['color'] = color

		if not text == None and len(text) > 0:
			attachment['text'] = text

		attachments_json = json.dumps(attachments)

		channels = channel_override
		if channels == None or len(channels.strip()) == 0:
			channels = self._settings.get(['channel'], merged=True)
		if not channels:
			channels = ''

		self._logger.debug("Slack API postMessage - Channels: " + channels + ", JSON: " + attachments_json)

		slack_identity_config = self._settings.get(['slack_identity'], merged=True)
		slack_as_user = slack_identity_config['existing_user']
		slack_icon_url = ''
		slack_icon_emoji = ''
		slack_username = ''

		if not slack_as_user:
			if 'icon_url' in slack_identity_config:
				slack_icon_url = slack_identity_config['icon_url']
			if not self.mattermost_mode() and 'icon_emoji' in slack_identity_config:
				slack_icon_emoji = slack_identity_config['icon_emoji']
			if 'username' in slack_identity_config:
				slack_username = slack_identity_config['username']
	
		for channel in channels.split(","):
			channel = channel.strip()
			if len(channel) == 0:
				continue

			if not slackAPIToken == None and len(slackAPIToken) > 0:
				try:
					slackAPIConnection = Slacker(slackAPIToken)
	
					apiRsp = slackAPIConnection.chat.post_message(channel, 
						text='', 
						username=slack_username,
						as_user=slack_as_user,
						attachments=attachments_json,
						icon_url=slack_icon_url,
						icon_emoji=slack_icon_emoji)

					self._logger.debug("Slack API message send response: " + apiRsp.raw)
				except Exception as e:
					self._logger.exception("Slack API message send error: " + str(e))
			elif not slackWebHookUrl == None and len(slackWebHookUrl) > 0:
				slack_msg = {}
				slack_msg['channel'] = channel
	
				if not slack_as_user == None:
					slack_msg['as_user'] = slack_as_user
				if not slack_icon_url == None and len(slack_icon_url) > 0:
					slack_msg['icon_url'] = slack_icon_url
				if not slack_icon_emoji == None and len(slack_icon_emoji) > 0:
					slack_msg['icon_emoji'] = slack_icon_emoji
				if not slack_username == None and len(slack_username) > 0:
					slack_msg['username'] = slack_username

				slack_msg['attachments'] = attachments
				self._logger.debug("Slack WebHook postMessage json: " + json.dumps(slack_msg))
	
				try:
					webHook = IncomingWebhook(slackWebHookUrl)
					webHookRsp = webHook.post(slack_msg)

					if not webHookRsp.ok:
						self._logger.error("Slack WebHook message send failed: " + webHookRsp.text)
				except Exception as e:
					self._logger.exception("Slack WebHook message send error: " + str(e))

	def upload_snapshot(self):
		snapshot_upload_method = self._settings.get(['snapshot_upload_method'], merged=True)
		if snapshot_upload_method == None or snapshot_upload_method == "NONE":
			return None, None

		local_file_path, snapshot_errors = self.retrieve_snapshot_images()
		
		if snapshot_errors == None:
			snapshot_errors = []
	
		if local_file_path:
			try:
				snapshot_upload_method = self._settings.get(['snapshot_upload_method'], merged=True)
				if snapshot_upload_method == 'S3':
					try:
						self._logger.debug("Uploading snapshot via S3")

						s3_upload_start = time.time()

						s3_config = self._settings.get(['s3_config'], merged=True)

						awsAccessKey = s3_config['AWSAccessKey']
						awsSecretKey = s3_config['AWSsecretKey']
						s3Bucket = s3_config['s3Bucket']
						fileExpireDays = int(s3_config['file_expire_days'])

						s3_expiration = timedelta(days=fileExpireDays)
					
						imgData = open(local_file_path,'rb')

						uploadFilename = "Snapshot_" + str(uuid.uuid1()).replace("-", "") + ".png"

						s3conn = tinys3.Connection(awsAccessKey, awsSecretKey, tls=True)
						s3UploadRsp = s3conn.upload(uploadFilename, imgData, s3Bucket,
							headers={ 'x-amz-acl' : 'public-read' }, expires=s3_expiration )

						self._logger.debug("S3 upload response: " + str(s3UploadRsp))
						s3_upload_elapsed = time.time() - s3_upload_start
						self._logger.debug("Uploaded snapshot to S3 in " + str(round(s3_upload_elapsed, 2)) + " seconds")

						return "https://s3.amazonaws.com/" + s3Bucket + "/" + uploadFilename, snapshot_errors
					except Exception as e:
						self._logger.exception("Failed to upload snapshot to S3: " + str(e))
						snapshot_errors.append("S3 error: " + str(e))
				elif snapshot_upload_method == 'MINIO':
					try:
						self._logger.debug("Uploading snapshot via Minio")

						minio_upload_start = time.time()

						minio_config = self._settings.get(['minio_config'], merged=True)

						minioAccessKey = minio_config['AccessKey']
						minioSecretKey = minio_config['SecretKey']
						minioBucket = minio_config['Bucket']
						if minio_config['secure']:
							minioURI = 'https://{endpoint}/{bucket}/'.format(endpoint=minio_config['Endpoint'],
																			bucket=minioBucket)
						else:
							minioURI = 'http://{endpoint}/{bucket}/'.format(endpoint=minio_config['Endpoint'],
																			bucket=minioBucket)
						uploadFilename = "Snapshot_" + str(uuid.uuid1()).replace("-", "") + ".png"

						minioClient = Minio(minio_config['Endpoint'],
											access_key=minioAccessKey,
											secret_key=minioSecretKey,
											secure=minio_config['secure'])
						minioUploadRsp = minioClient.fput_object(minioBucket,
															  uploadFilename,
															  local_file_path)

						self._logger.debug("Minio upload response: " + str(minioUploadRsp))
						minio_upload_elapsed = time.time() - minio_upload_start
						self._logger.debug(
							"Uploaded snapshot to Minio in " + str(round(minio_upload_elapsed, 2)) + " seconds")

						return minioURI + uploadFilename, snapshot_errors
					except Exception as e:
						self._logger.exception("Failed to upload snapshot to Minio: " + str(e))
						snapshot_errors.append("Minio error: " + str(e))
				elif snapshot_upload_method == "IMGUR":
					try:
						self._logger.debug("Uploading snapshot via Imgur")

						imgur_upload_start = time.time()

						imgur_config = self._settings.get(['imgur_config'], merged=True)

						imgur_client_id = imgur_config['client_id']
						imgur_client_secret = imgur_config['client_secret']
						imgur_client_refresh_token = imgur_config['refresh_token']
						imgur_album_id = imgur_config['album_id']

						if imgur_client_refresh_token == None or len(imgur_client_refresh_token.strip()) == 0:
							imgur_client_refresh_token = None
						else:
							imgur_client_refresh_token = imgur_client_refresh_token.strip()

						if imgur_album_id == None or len(imgur_album_id.strip()) == 0:
							imgur_album_id = None
						else:
							imgur_album_id = imgur_album_id.strip()

						imgur_client = ImgurClient(imgur_client_id, imgur_client_secret, None, imgur_client_refresh_token)
						self.tmp_imgur_client = imgur_client

						imgur_upload_config = { }
						if not imgur_album_id == None:
							imgur_upload_config['album'] = imgur_album_id

						##imgur_upload_config['title'] = 'ImageTitle123'
						##imgur_upload_config['description'] = 'ImageDescription123'

						self._logger.debug("Uploading to Imgur - Config: " + str(imgur_upload_config) + ", File path: " + local_file_path + ", File exists: " + str(os.path.isfile(local_file_path)))

						imgurUploadRsp = imgur_client.upload_from_path(local_file_path, config=imgur_upload_config, anon=False)
						self._logger.debug("Imgur upload response: " + str(imgurUploadRsp))

						imgur_upload_elapsed = time.time() - imgur_upload_start
						self._logger.debug("Uploaded snapshot to Imgur in " + str(round(imgur_upload_elapsed, 2)) + " seconds")
					
						imgurUrl = imgurUploadRsp['link']
						return imgurUrl, snapshot_errors
					except ImgurClientError as ie:
						self._logger.exception("Failed to upload snapshot to Imgur (ImgurClientError): " + str(ie.error_message) + ", StatusCode: " + str(ie.status_code))
						self._logger.exception("ImgurError: " + str(self.tmp_imgur_client.credits))
						snapshot_errors.append("Imgur error: " + str(ie.error_message))
					except ImgurClientRateLimitError as rle:
						self._logger.exception("Failed to upload snapshot to Imgur (ImgurClientRateLimitError): " + str(e))
						snapshot_errors.append("Imgur error: " + str(e))
					except Exception as e:
						self._logger.exception("Failed to upload snapshot to Imgur (Exception): " + str(e))
						snapshot_errors.append("Imgur error: " + str(e))
			except Exception as e:
				self._logger.exception("Snapshot capture error: %s" % str(e))
				snapshot_errors.append("Snapshot error: " + str(e.message))
			finally:
				if not local_file_path == None:
					os.remove(local_file_path)
		return None, snapshot_errors

	def retrieve_snapshot_images(self):
		urls = []

		localCamera = self._settings.globalGet(["webcam", "snapshot"])
		localCameraFlipH = self._settings.globalGet(["webcam", "flipH"])
		localCameraFlipV = self._settings.globalGet(["webcam", "flipV"])
		localCameraRotate90 = self._settings.globalGet(["webcam", "rotate90"])

		if not localCamera == None:
			urls.append((localCamera, localCameraFlipH, localCameraFlipV, localCameraRotate90))

		additional_snapshot_urls = self._settings.get(['additional_snapshot_urls'], merged=True)
		if not additional_snapshot_urls == None:
			for url in additional_snapshot_urls.split(","):
				url = url.strip()
				if len(url) > 0:
					urls.append((urllib2.unquote(url), False, False, False))
		
		self._logger.debug("Snapshot URLs: " + str(urls))

		threads = []
		thread_responses = []
		downloaded_images = []
		snapshot_errors = []
		download_start = time.time()

		idx = 0
		for url_data in urls:
			url, flip_h, flip_v, rotate_90 = url_data

			thread_responses.append((None,None))

			t = threading.Thread(target=self.download_image, args=(url, flip_h, flip_v, rotate_90, idx, thread_responses))
			t.setDaemon(True)
			threads.append(t)
			t.start()

			idx += 1

		for t in threads:
			t.join()

		download_elapsed = time.time() - download_start
		self._logger.debug("Downloaded all " + str(len(urls)) + " snapshots in " + str(round(download_elapsed, 2)) + " seconds")

		for (downloaded_image, error_msg) in thread_responses:
			if downloaded_image == None and error_msg == None:
				continue

			if not downloaded_image == None:
				downloaded_images.append(downloaded_image)
			if not error_msg == None:
				snapshot_errors.append(error_msg)

		## The single returned image will be deleted by the caller

		if len(downloaded_images) == 0:
			return None, None

		if len(downloaded_images) > 1:
			## downloaded_images will be deleted internally by combine_images
			combined_image, error_msg = self.combine_images(downloaded_images)
			if not error_msg == None:
				snapshot_errors.append(error_msg)
			return combined_image, snapshot_errors
		else:
			return downloaded_images[0], snapshot_errors

	def download_image(self, url, flip_h, flip_v, rotate_90, rsp_idx, responses):
		imgData = None
		temp_fd = None
		temp_filename = None

		try:
			basic_auth_user = None
			basic_auth_pwd = None

			##If basic auth credentials were passed in via protocol://user:pwd@host:port/path, parse them out
			if "@" in url:
				first_split = url.split("@")
				host_port_path = first_split[1];

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
				

			imgReq = urllib2.Request(url)

			if not basic_auth_user == None and not basic_auth_pwd == None:
				auth_header = base64.b64encode('%s:%s' % (basic_auth_user, basic_auth_pwd))
				imgReq.add_header("Authorization", "Basic %s" % auth_header)

			imgRsp = urllib2.urlopen(imgReq, timeout=2)

			temp_fd, temp_filename = mkstemp()
			temp_file = open(temp_filename, "wb")
			temp_file.write(imgRsp.read())
			
			imgByteCount = temp_file.tell()

			temp_file.close()

			if flip_h or flip_v or rotate_90:
				tmp_img = Image.open(temp_filename)
				if flip_h:
					tmp_img = tmp_img.transpose(Image.FLIP_LEFT_RIGHT)
				if flip_v:
					tmp_img = tmp_img.transpose(Image.FLIP_TOP_BOTTOM)
				if rotate_90:
					tmp_img = tmp_img.transpose(Image.ROTATE_90)

				tmp_img.save(temp_filename, "JPEG")

			self._logger.debug("Downloaded snapshot from URL: " + url + " (" + octoprint.util.get_formatted_size(imgByteCount) + ") to " + temp_filename)

			responses[rsp_idx] = (temp_filename, None)
		except Exception as e:
			self._logger.exception("Error downloading snapshot - URL: " + url + ", Error: " + str(e))
			responses[rsp_idx] = (None, str(e))
		finally:
			if not imgData == None:
				imgData.close()
			if not temp_fd == None:
				os.close(temp_fd)
	
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
			
			widths, heights = zip(*(i.size for i in images))

			total_width = sum(widths)
			max_width = max(widths)
			total_height = sum(heights)
			max_height = max(heights)

			grid_size = 0,0
			grid_rows = None
			grid_row_images = []
			grid_row_heights = []
			grid_col_widths = []

			arrangement = self._settings.get(['snapshot_arrangement'], merged=True)
			if arrangement == None:
				arrangement = "HORIZONTAL"

			##Lazy grid layout (no formula) supports up to 12 images
			if arrangement == "GRID" and image_count > 12:
				arrangement = "HORIZONTAL"

			if arrangement == "VERTICAL":
				grid_size = image_count,1
			elif arrangement == "HORIZONTAL":
				grid_size = 1,image_count
			elif arrangement == "GRID":
				##The grid code is a mess but it was a quick and dirt solution we can rewrite later

				if image_count == 1:
					grid_size = 1,1
				elif image_count == 2:
					grid_size = 2,1
				elif image_count == 3:
					grid_size = 2,2
				elif image_count == 4:
					grid_size = 2,2
				elif image_count == 5:
					grid_size = 3,2
				elif image_count == 6:
					grid_size = 3,2
				elif image_count == 7:
					grid_size = 3,3
				elif image_count == 8:
					grid_size = 3,3
				elif image_count == 9:
					grid_size = 3,3
				elif image_count == 10:
					grid_size = 4,3
				elif image_count == 11:
					grid_size = 4,3
				elif image_count == 12:
					grid_size = 4,3
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

				width,height = img.size

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

			newWidth += (image_spacer * 2) ## outer borders
			newHeight += (image_spacer * 2) ## outer borders

			newWidth += (col_count - 1) * image_spacer ##horizontal spacers
			newHeight += (row_count - 1) * image_spacer ##vertical spacers


			new_im = Image.new('RGB', (newWidth, newHeight))

			x_offset = image_spacer
			y_offset = image_spacer
	
			if arrangement == "VERTICAL" or arrangement == "HORIZONTAL":
				for im in images:
					if arrangement == "VERTICAL":
						x_adjust = image_spacer
						if im.size[0] != max_width:
							x_adjust = (max_width - im.size[0]) / 2

						new_im.paste(im, (x_adjust,y_offset))
						y_offset += im.size[1]
						y_offset += image_spacer
					elif arrangement == "HORIZONTAL":
						y_adjust = image_spacer
						if im.size[1] != max_height:
							y_adjust = (max_height - im.size[1]) / 2

						new_im.paste(im, (x_offset,y_adjust))
						x_offset += im.size[0]
						x_offset += image_spacer
			elif arrangement == "GRID":
				row_idx = 0
				col_idx = 0

				for im in images:
					width,height = im.size

					row_height = max(grid_row_heights[row_idx])
					col_width = max(grid_col_widths[col_idx])

					x_adjust = 0
					if width < col_width:
						x_adjust = (col_width - width) / 2

					y_adjust = 0
					if height < row_height:
						y_adjust = (row_height - height) / 2

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
			new_im.save(temp_filename, "JPEG")

			statinfo = os.stat(temp_filename)
			new_img_size = statinfo.st_size

			generate_image_elapsed = time.time() - generate_image_start
			self._logger.debug("Generated combined image (" + octoprint.util.get_formatted_size(new_img_size)  + ") in " + str(round(generate_image_elapsed, 2)) + " seconds")

			for im in images:
				im.close()
			
			for tmpFile in local_paths:
				os.remove(tmpFile)

			return temp_filename, None
		except Exception as e:
			self._logger.exception("Error generating combined snapshot image: %s" % (str(e)))
			return None, str(e.message)
		finally:
			if not temp_fd == None:
				os.close(temp_fd)


def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = OctoslackPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}
