 /*
 * View model for OctoPrint-Octoslack
 *
 * Author: Chris Fraschetti
 * License: Apache2
 */
$(function() {
    function OctoslackViewModel(parameters) {
        var self = this;

        self.onStartup = function() {
            Octoslack.onStartup();
        };

        self.onAfterBinding = function() {
            Octoslack.afterBindingInit();
        };

	self.onEventSettingsUpdated  = function() {
            Octoslack.afterSettingsSaved();
	};

        self.onSettingsBeforeSave = function() {
            Octoslack.beforeSave();
        };
    }

    // view model class, parameters for constructor, container to bind to
    OCTOPRINT_VIEWMODELS.push([
        OctoslackViewModel,
        ["settingsViewModel"]
    ]);
});

var Octoslack = {

    onStartup : function() {
	this.buildOctoPrintEventConfigs();
    },

    last_connection_method : null,
    last_bot_commands : null,

    afterBindingInit : function() {
        this.setInitialInputStates();
        this.buildSnapshotURLsTable();
        this.buildGcodeEventsTable();
	this.applyMattermostChanges();
	this.populateTimezones();

	this.last_connection_method = $("#octoslack_connection_method_hidden").val();
	this.last_bot_commands = $("#octoslack_bot_commands").is(":checked");

        this.changeImgurClientID();
        $("#octoslack_imgur_refresh_token").bind('input propertychange', function() { Octoslack.changeImgurRefreshToken(); });
        $("#octoslack_imgur_album_id").bind('input propertychange', function() { Octoslack.changeImgurAlbumID(); });

        this.changeConnectionType();
	this.changeSnapshotUploadMethod();
    },

    setInitialInputStates : function() {
	var connection_method = $("#octoslack_connection_method_hidden").val();
        var connection_radio = $("input[name=octoslack_connection_type][value=" + connection_method + "]");
	connection_radio.attr('checked', 'checked');
        connection_radio.trigger('click');

	var slack_identity_check= $("#octoslack_slack_identity_check")[0];
	this.toggleUseSlackIdentity(slack_identity_check);

	var upload_method = $("#octoslack_upload_method_hidden").val();
        var upload_method_radio = $("input[name=octoslackSnapshotUploadMethod][value=" + upload_method + "]");
	upload_method_radio.attr('checked', 'checked');
        upload_method_radio.trigger('click');

	var s3_retention = $("#octoslack_s3_retention");
	if (s3_retention.val() <= 0) {
	    s3_retention.val("60");
	    s3_retention.trigger('change');
        }
    },

    applyMattermostChanges : function() {
        var mattermost_enabled = $("#octoslack_mattermost_compatabilty_mode").is(":checked");

	if(mattermost_enabled) {
		$('#octoslack_connection_type_webhook').trigger('click');

		$('#octoslack_connection_type_apitoken').attr('disabled', 'disabled');
		$('#octoslack_connection_type_webhook').attr('disabled', 'disabled');
		
		$('#octoslack_custom_identity_icon_emoji').attr('disabled', 'disabled');
	} else {
		$('#octoslack_connection_type_apitoken').removeAttr('disabled');
		$('#octoslack_connection_type_webhook').removeAttr('disabled');
		$('#octoslack_custom_identity_icon_emoji').removeAttr('disabled');
	}
    },

    applySlackUploadChanges : function() {
        var upload_method = $("#octoslack_upload_method_hidden").val();

        var showProgressUpdateMethod = false;
        var showProgressImageUpdateInterval = false;

        if(upload_method == "SLACK") {
            showProgressUpdateMethod = true;
            showProgressImageUpdateInterval = true;
        }

        var progress_update_method_div = $("#octoslack_progress_update_method");
        var progress_image_update_interval_div = $("#octoslack_progress_image_update_interval");

        if(showProgressUpdateMethod) {
            progress_update_method_div.attr("class", "octoprint_config_row");
        } else {
            progress_update_method_div.attr("class", "octoslack_hidden");
        }

        if(showProgressImageUpdateInterval) {
            progress_image_update_interval_div.attr("class", "octoprint_config_row");
        } else {
            progress_image_update_interval_div.attr("class", "octoslack_hidden");
        }
    },

    populateTimezones : function() {
        var timezones_str = $("#octoslack_timezones_hidden").val();
        var timezones_arr = timezones_str.split('|');

        var timezones_select = $("#octoslack_timezones");

        timezones_select.append($('<option>', {
            value: 'OS_Default',
            text: 'OS_Default',
        }));

        for(var i = 0; i < timezones_arr.length; i++) {
            var opt = timezones_arr[i];

            timezones_select.append($('<option>', {
                value: opt,
                text: opt,
            }));
        }

        var selected_timezone = $("#octoslack_timezone_hidden").val();
        timezones_select.val(selected_timezone);
    },

    timezone_change : function() {
        var selected_timezone = $("#octoslack_timezones").val();

        $("#octoslack_timezone_hidden").val(selected_timezone);
        $("#octoslack_timezone_hidden").trigger('change');
    },

    beforeSave : function() {
        this.storeGcodeEvents();
    },

    afterSettingsSaved : function() {
	var new_connection_method = $("#octoslack_connection_method_hidden").val();
	var new_channel = $("#octoslack_channel").val();

	if(new_connection_method == "APITOKEN" && new_channel.trim().length == 0) {
		var title = "Required Octoslack field not populated";
		var text = "When using the API Token for Slack connectivity, a Slack channel must be provided";
		var message = $("<p></p>")
                	.append(text);
            	showMessageDialog({
                	title: gettext(title),
                	message: message
            	});
	}

 	var restart_needed = false;

	var new_bot_commands = $("#octoslack_bot_commands").is(":checked");
	var apitoken_set = $('#octoslack_apitoken').val().trim().length > 0;

	if(this.last_connection_method == "APITOKEN" && apitoken_set && (this.last_bot_commands != new_bot_commands))
		restart_needed = true;
	else if(this.last_connection_method == "APITOKEN" && new_connection_method != "APITOKEN" && apitoken_set && this.last_bot_commands)
		restart_needed = true;
	else if(this.last_connection_method != "APITOKEN" && new_connection_method == "APITOKEN" && apitoken_set && new_bot_commands)
		restart_needed = true;

	this.last_connection_method = $("#octoslack_connection_method_hidden").val();
	this.last_bot_commands = $("#octoslack_bot_commands").is(":checked");

	if(restart_needed) {
		var title = "OctoPrint restart required";
		var text = "A change to an Octoslack setting requiring an OctoPrint restart has been changed. The new setting value will not take effect until OctoPrint has been restarted";
		var message = $("<p></p>")
                	.append(text);
            	showMessageDialog({
                	title: gettext(title),
                	message: message
            	});
	}
    },

    allow_slack_msg_attrs : function() {
	var connection_method = $("#octoslack_connection_method_hidden").val();
	switch(connection_method) {
	    case "APITOKEN":
	    case "WEBHOOK":
	        return true;
	}

	return false;
    },

    allow_pushover_msg_attrs : function() {
	var connection_method = $("#octoslack_connection_method_hidden").val();
	return connection_method == "PUSHOVER";
    },

    changeConnectionType : function(new_type) {
        if (new_type === undefined)
            new_type = $("#octoslack_connection_method_hidden").val();

        var slack_config_section = $("#octoslack_slack_config_section");
        var pushbullet_config_section = $("#octoslack_pushbullet_config_section");
        var pushover_config_section = $("#octoslack_pushover_config_section");
        var rocketchat_config_section = $("#octoslack_rocketchat_config_section");

        slack_config_section.attr("class", "octoslack_hidden");
        pushbullet_config_section.attr("class", "octoslack_hidden"); 
        pushover_config_section.attr("class", "octoslack_hidden"); 
        rocketchat_config_section.attr("class", "octoslack_hidden"); 

        var mattermost_enabled = $("#octoslack_mattermost_compatabilty_mode").is(":checked");
	if(mattermost_enabled)
		new_type = "WEBHOOK";
        var mattermost_enabled = $("#octoslack_mattermost_compatabilty_mode").is(":checked");

        var apiTokenGroup = $("#octoslack_apitoken_group");
        var webhookGroup = $("#octolack_webhook_group");

	var slackUploadOption = $("#octoslackSlackUploadMethod");
	var pushbulletUploadOption = $("#octoslackPushbulletUploadMethod");
	var pushoverUploadOption = $("#octoslackPushoverUploadMethod");
	var rocketChatUploadOption = $("#octoslackRocketChatUploadMethod");

        apiTokenGroup.attr("class", "octoslack_hidden");
        webhookGroup.attr("class", "octoslack_hidden");

        slackUploadOption.attr("class", "octoslack_hidden"); 
        pushbulletUploadOption.attr("class", "octoslack_hidden"); 
        pushoverUploadOption.attr("class", "octoslack_hidden"); 
        rocketChatUploadOption.attr("class", "octoslack_hidden"); 


        switch (new_type) {
            case "APITOKEN":
                slack_config_section.attr("class", "octoslack_visible");
                apiTokenGroup.attr("class", "octoslack_visible");
                slackUploadOption.attr("class", "octoslack_visible");
                break;
           case "WEBHOOK":
                slack_config_section.attr("class", "octoslack_visible");
                webhookGroup.attr("class", "octoslack_visible");
                break;
           case "PUSHBULLET":
                pushbullet_config_section.attr("class", "octoslack_visible");
                pushbulletUploadOption.attr("class", "octoslack_visible");
                break;
           case "PUSHOVER":
                pushover_config_section.attr("class", "octoslack_visible");
                pushoverUploadOption.attr("class", "octoslack_visible");
                break;
           case "ROCKETCHAT":
                rocketchat_config_section.attr("class", "octoslack_visible");
                rocketChatUploadOption.attr("class", "octoslack_visible");
                break;
        }

        var connection_method_hidden = $("#octoslack_connection_method_hidden");
        connection_method_hidden.val(new_type);
        connection_method_hidden.trigger('change');

	//Not all services support all config items
	var allow_slack_attrs = Octoslack.allow_slack_msg_attrs();
	$( "div[octoslack_msg_slack]" ).each(function() {
	    $(this).attr("class", allow_slack_attrs ? "octoprint_config_row octoslack_visible" : "octoprint_config_row octoslack_hidden");
	});

	var allow_pushover_attrs = Octoslack.allow_pushover_msg_attrs();
	$( "div[octoslack_msg_pushover]" ).each(function() {
	    $(this).attr("class", allow_pushover_attrs ? "octoprint_config_row octoslack_visible" : "octoprint_config_row octoslack_hidden");
	});
    },

    toggleUseSlackIdentity : function(checkbox) {
        var checked = checkbox.checked;
        var custom_identity_div = $("#octoslack_custom_identity_group");

        custom_identity_div.attr("class", checked ? "octoslack_hidden" : "octoslack_visible");
    },

    changeSnapshotUploadMethod : function(selection) {
        if (selection === undefined)
            selection = $("#octoslack_upload_method_hidden").val();

        var imgurGroup = $("#octoslack_imgur_group");
        var s3Group = $("#octolack_s3_group");
        var minioGroup = $("#octolack_minio_group");

        imgurGroup.attr("class", "octoslack_hidden");
        s3Group.attr("class", "octoslack_hidden");
        minioGroup.attr("class", "octoslack_hidden");

	var allow_timelapse_upload = false;

        var upload_timelapse_section = $("#octoslack_upload_timelapse");
        upload_timelapse_section.attr("class", "octoslack_hidden");

        switch (selection.value) {
            case "IMGUR":
                imgurGroup.attr("class", "octoslack_visible");
                break;
            case "S3":
                s3Group.attr("class", "octoslack_visible");
	        allow_timelapse_upload = true;
                break;
            case "MINIO":
                minioGroup.attr("class", "octoslack_visible");
	        allow_timelapse_upload = true;
                break;
            case "SLACK":
	        allow_timelapse_upload = true;
                break;
            case "PUSHBULLET":
	        allow_timelapse_upload = true;
                break;
            case "PUSHOVER":
                break;
            case "ROCKETCHAT":
                break;
        }

	$( "div[octoslack_timelapse_upload]" ).each(function() {
	    $(this).attr("class", allow_timelapse_upload ? "octoprint_config_row octoslack_visible" : "octoprint_config_row octoslack_hidden");
	});

        var upload_method = $("#octoslack_upload_method_hidden");
        upload_method.val(selection.value);
        upload_method.trigger('change');

        Octoslack.applySlackUploadChanges();
    },

    escapeHtml : function(html_text) {
        var text_elem = document.createTextNode(html_text);
        var div_elem = document.createElement('div');
        div_elem.appendChild(text_elem);
        return div_elem.innerHTML;
    },

    changeImgurClientID : function() {
        var client_id = $("#octoslack_imgur_client_id").val();
        client_id = client_id.trim();

        var auth_link = $("#octoslack_imgur_auth_link");

	if(client_id.length > 0) {
            var authUrl = "https://api.imgur.com/oauth2/authorize?client_id=" + client_id + "&response_type=token";
            auth_link.attr('href', authUrl);
            auth_link.attr('target', "_blank");
        } else {
            auth_link.attr('href', "javascript:Octoslack.showMissingImgurClientIDDialog()");
            auth_link.removeAttr('target');
        }
    },

    imgurRefreshTokenRegex : new RegExp('refresh_token=([^&]+)'),

    changeImgurRefreshToken : function() {
        var refresh_token_elem = $("#octoslack_imgur_refresh_token");
        var refresh_token = refresh_token_elem.val();
        refresh_token = refresh_token.trim();

        //Handle pasted app auth urls
        if(!refresh_token.toLowerCase().startsWith("http"))
            return;

        var matches = this.imgurRefreshTokenRegex.exec(refresh_token);
	if(matches.length > 1) {
            refresh_token = matches[1];
            refresh_token = refresh_token.trim();
    
            //Don't allow a loop of checking for http
            if(refresh_token.toLowerCase().startsWith("http"))
                return;

            refresh_token_elem.val(refresh_token);
            refresh_token_elem.trigger('change');
        }
    },

    imgurAlbumIDRegex : new RegExp('/a/([^&]+)'),

    changeImgurAlbumID : function() {
        var album_id_elem = $("#octoslack_imgur_album_id");
        var album_id = album_id_elem.val();
        album_id = album_id.trim();

        //Handle pasted album urls
        if(!album_id.toLowerCase().startsWith("http"))
            return;

        var matches = this.imgurAlbumIDRegex.exec(album_id);
	if(matches.length > 1) {
            album_id = matches[1];
            album_id = album_id.trim();
    
            //Don't allow a loop of checking for http
            if(album_id.toLowerCase().startsWith("http"))
                return;

            album_id_elem.val(album_id);
            album_id_elem.trigger('change');
        }
    },

    showMissingImgurClientIDDialog() {
        var title = "Required Octoslack field not populated";
        var text = "When using the API Token for Slack connectivity, a Slack channel must be provided";
        var message = $("<p></p>")
                .append(text);
        showMessageDialog({
                title: gettext(title),
                message: message
        });
    },
    buildOctoPrintEventConfigs : function() {
	var events = [
		{ "InternalName" : "PrintStarted", "DisplayName" : "Print started" },
		{ "InternalName" : "PrintFailed", "DisplayName" : "Print failed" },
		{ "InternalName" : "PrintCancelled", "DisplayName" : "Print cancelled" },
		{ "InternalName" : "PrintPaused", "DisplayName" : "Print paused" },
		{ "InternalName" : "PrintResumed", "DisplayName" : "Print resumed" },
		{ "InternalName" : "PrintDone", "DisplayName" : "Print finished" },
		{ "InternalName" : "Progress", "DisplayName" : "Print progress" },
		{ "InternalName" : "Heartbeat", "DisplayName" : "Printer status heartbeat" },
		{ "InternalName" : "MovieRendering", "DisplayName" : "Timelapse render started" },
		{ "InternalName" : "MovieDone", "DisplayName" : "Timelapse render finished" },
		{ "InternalName" : "MovieFailed", "DisplayName" : "Timelapse render failed" },
		{ "InternalName" : "Error", "DisplayName" : "OctoPrint error" },
		{ "InternalName" : "Startup", "DisplayName" : "OctoPrint started" },
		{ "InternalName" : "Shutdown", "DisplayName" : "OctoPrint stopped" },
		{ "InternalName" : "Connecting", "DisplayName" : "Printer connecting" },
		{ "InternalName" : "Connected", "DisplayName" : "Printer connected" },
		{ "InternalName" : "Disconnecting", "DisplayName" : "Printer disconnecting" },
		{ "InternalName" : "Disconnected", "DisplayName" : "Printer disconnected" },
	];

	var eventsHtml = this.buildOctoPrintEventConfigRow('STANDARD', events, null, null);
        
        var events_container = $("#octoslack_events_container");
        events_container.attr("class", "octoslack_visible");
        events_container.html(eventsHtml);
    },

    updateGcodeEventTitle : function(internalName) {
        if(!internalName) return;

	internalName = internalName.trim();
	if(internalName.length == 0) return;

        var gcodeElemId = "octoslack_event_" + internalName + "_gcode";
	var gcodeTypeElemId = "octoslack_event_" + internalName + "_gcode_type";
        var titleElemId = "octoslack_event_" + internalName + "_gcode_title";

        var gcodeElem = $("#" + gcodeElemId);
        if (gcodeElem == undefined) return;

        var gcodeTypeElem = $("#" + gcodeTypeElemId);
        if (gcodeTypeElem == undefined) return;

        var titleElem = $("#" + titleElemId);
        if (titleElem == undefined) return;

	var gcodeVal = gcodeElem.val().trim();
	var typeVal = gcodeTypeElem.val().trim();

        var newTitle = this.buildGcodeEventTitle(gcodeVal, typeVal);

        titleElem.text(newTitle);
    },

    buildGcodeEventTitle : function(gcode, type) {
        if(type == "sent")
            type = "Sent";
        else
            type = "Received";

        var newTitle;
        if (gcode.length == 0)
            newTitle = "...";
        else
            newTitle = "[" + type + "] " + this.escapeHtml(gcode);

        return newTitle;
    },

    buildOctoPrintEventConfigRow : function(eventType, events, action_text, action_handler) {

        var useDataBind = false;

	var eventHtml = [];

        if(events == null || events == undefined)
            events = [];

        var pushoversounds = [
		["pushover", "Pushover (default)"],
		["bike", "Bike"],
		["bugle", "Bugle"],
		["cashregister", "Cash Register"],
		["classical", "Classical"],
		["cosmic", "Cosmic"],
		["falling", "Falling"],
		["gamelan", "Gamelan"],
		["incoming", "Incoming"],
		["intermission", "Intermission"],
		["magic", "Magic"],
		["mechanical", "Mechanical"],
		["pianobar", "Piano Bar"],
		["siren", "Siren"],
		["spacealarm", "Space Alarm"],
		["tugboat", "Tug Boat"],
		["alien", "Alien Alarm (long)"],
		["climb", "Climb (long)"],
		["persistent", "Persistent (long)"],
		["echo", "Pushover Echo (long)"],
		["updown", "Up Down (long)"],
		["none", "None (silent)"]
        ];

        var pushoverpriorities = [
		["-2", "Lowest Priority"],
		["-1", "Low Priority"],
		["0", "Normal Priority"],
		["1", "High Priority"],
		["2", "Emergency Priority"]
        ];

	for(var i = 0; i < events.length; i++) {
	    var event = events[i];

	    var internalName = event.InternalName;
            var customEnabled = false;
            var customChannelOverride = "";
            var customCaptureSnapshot = false;
            var customMessage = "";
            var customFallback = "";
            var customPushoverSound = ""
	    var customPushoverPriority = ""

            if(eventType == "STANDARD") {
                useDataBind = true;
	        var displayName = event.DisplayName;
	        eventHtml.push("        <h3>" + this.escapeHtml(displayName) + "</h3>");
            }

            var rowContainerId = eventType + "_" + internalName + "_row";

	    eventHtml.push("        <div id='" + rowContainerId + "' internalname='" + internalName + "'>");

            if(eventType == "GCODE") {
	        var gcode = event.Gcode;
	        var gcodeMatchType = event.GcodeMatchType;
	        var gcodeType = event.GcodeType;
                var customColor = event.Color
                customEnabled = event.Enabled;
                customChannelOverride = event.ChannelOverride;
                customCaptureSnapshot = event.CaptureSnapshot;
                customMessage = event.Message;

                customFallback = event.Fallback;
                if(customFallback === undefined)
                    customFallback = '';

                customPushoverSound = event.PushoverSound;
		if(customPushoverSound === undefined)
                    customPushoverSound = '';
		else
                    customPushoverSound = customPushoverSound.trim();

		customPushoverPriority = event.PushoverPriority;
		if(customPushoverPriority=== undefined)
                    customPushoverPriority = '';
		else
                    customPushoverPoriority = customPushoverPriority.trim();

                if(gcode == undefined)
                    gcode = "";
	        eventHtml.push("        <h3><span id='octoslack_event_" + internalName + "_gcode_title'>" + this.buildGcodeEventTitle(gcode, gcodeType) + "</span></h3>");
            }

            //Enabled
	    eventHtml.push("        <div class='octoprint_config_row'>");
	    eventHtml.push("            <input type='checkbox' class='octoslack_valign octoslack_checkbox_margin_override' id='octoslack_event_" + internalName + "_enabled' "
                + (useDataBind ? "data-bind='checked: settings.plugins.Octoslack.supported_events." + internalName + ".Enabled'" : "")
                + (customEnabled ? " checked " : " ")
                + ">");
	    eventHtml.push("            <div class='octoslack_label octoslack_action_label' onclick=\"$('#octoslack_event_" + internalName + "_enabled').trigger('click')\">Enabled</div>");
	    eventHtml.push("        </div>");

            if(eventType == "GCODE") {
	        var gcode = event.Gcode;
                if(gcode == undefined)
                    gcode = "";

		var gcodeTitleHandler = "Octoslack.updateGcodeEventTitle(\"" + internalName + "\");";

                //GcodeType
	        eventHtml.push("        <div class='octoprint_config_row'>");
	        eventHtml.push("            <select class='octoslack_select' id='octoslack_event_" + internalName + "_gcode_type' onchange='" + gcodeTitleHandler + "'>");
	        eventHtml.push("                <option value='sent'" + (!gcodeType || gcodeType == 'sent' ? ' selected' : '') + ">G-code sent</option>");
	        eventHtml.push("                <option value='received'" + (gcodeType == 'received' ? ' selected' : '') + ">G-code received</option>");
	        eventHtml.push("            </select>");
	        eventHtml.push("            <div class='octoslack_label'>G-code type</div>");
	        eventHtml.push("            <br/>");
	        eventHtml.push("            <small class='muted'>");
	        eventHtml.push("                G-code sent = Commands sent from OctoPrint to the printer");
	        eventHtml.push("                <br/>");
	        eventHtml.push("                G-code received = Commands/data received from the printer");
	        eventHtml.push("            </small>");
	        eventHtml.push("        </div>");

                //GcodeMatchType
	        eventHtml.push("        <div class='octoprint_config_row'>");
	        eventHtml.push("            <select class='octoslack_select' id='octoslack_event_" + internalName + "_gcode_match_type'>");
	        eventHtml.push("                <option value='StartsWith'" + (!gcodeMatchType || gcodeMatchType == 'StartsWith' ? ' selected' : '') + ">Starts with</option>");
	        eventHtml.push("                <option value='EndsWith'" + (gcodeMatchType == 'EndsWith' ? ' selected' : '') + ">Ends with</option>");
	        eventHtml.push("                <option value='Contains'" + (gcodeMatchType == 'Contains' ? ' selected' : '') + ">Contains</option>");
	        eventHtml.push("                <option value='Regex'" + (gcodeMatchType == 'Regex' ? ' selected' : '') + ">Regular expression</option>");
	        eventHtml.push("            </select>");
	        eventHtml.push("            <div class='octoslack_label'>G-code match type</div>");
                eventHtml.push("            <br/>");
                eventHtml.push("            <small class='muted'>");
                eventHtml.push('                NOTE: Inefficient regular expressions can incur long execution times which may block OctoPrint\'s communication with your printer.');
                eventHtml.push("            </small>");
	        eventHtml.push("        </div>");

                //Gcode
	        eventHtml.push("        <div class='octoprint_config_row'>");
	        eventHtml.push("            <input type='text' size='30' id='octoslack_event_" + internalName + "_gcode' onkeydown='" + gcodeTitleHandler + "' onpaste='" + gcodeTitleHandler + "' oninput='" + gcodeTitleHandler + "' onchange='" + gcodeTitleHandler + "' "
                    + (useDataBind ? "data-bind='value: settings.plugins.Octoslack.supported_events." + internalName + ".Gcode'" : "") 
                    + " value='" + this.escapeHtml(gcode.trim()) + "'>");
	        eventHtml.push("            <div class='octoslack_label octoslack_action_label'>G-code</div>");
                eventHtml.push("            <br/>");
                eventHtml.push("            <small class='muted'>");
                eventHtml.push('                The G-code/text pattern or regular expression to match against sent/received G-code.');
                eventHtml.push("            </small>");
	        eventHtml.push("        </div>");

                //Color
	        eventHtml.push("        <div class='octoprint_config_row' octoslack_msg_slack>");
	        eventHtml.push("            <select class='octoslack_select' id='octoslack_event_" + internalName + "_color'>");
	        eventHtml.push("                <option value='good'" + (customColor == 'good' ? ' selected' : '') + ">OK</option>");
	        eventHtml.push("                <option value='warning'" + (customColor == 'warning' ? ' selected' : '') + ">Warning</option>");
	        eventHtml.push("                <option value='danger'" + (customColor == 'danger' ? ' selected' : '') + ">Error</option>");
	        eventHtml.push("            </select>");
	        eventHtml.push("            <div class='octoslack_label'>Status level</div>");
	        eventHtml.push("        </div>");
            }

            if(eventType == "STANDARD" && internalName == "Progress") {
                // Update method (inplace, or new messagse)
            eventHtml.push("        <div id='octoslack_progress_update_method' class='octoprint_config_row'>");
            eventHtml.push("            <select class='octoslack_select' id='octoslack_event_" + internalName + "_UpdateMethod' "
                 + (useDataBind ? "data-bind='value: settings.plugins.Octoslack.supported_events." + internalName + ".UpdateMethod'" : "")
                 + " onchange='Octoslack.applySlackUploadChanges()'>");
            eventHtml.push("<option value='INPLACE'>In-place</option>");
            eventHtml.push("<option value='NEW_MESSAGE'>New Message</option>");
            eventHtml.push("</select>");
            eventHtml.push("            <div class='octoslack_label octoslack_action_label'>Progress Update Method</div>");
            eventHtml.push("            <br/>");
            eventHtml.push("            <small class='muted'>");
            eventHtml.push('                If "In-place" is selected, rather than sending a new message to update the progress, the existing message will be updated in place. Requires Slack API Token.');
            eventHtml.push("            </small>");
            eventHtml.push("        <br/>");
            eventHtml.push("        </div>");
             // Min image update interval
            eventHtml.push("        <div id='octoslack_progress_image_update_interval' class='octoprint_config_row'>");
            eventHtml.push("            <input type='number' step='any' min='0' max='1440' class='input-mini text-right' id='octoslack_event_" + internalName + "_SlackMinSnapshotUpdateInterval' "
                 + (useDataBind ? "data-bind='value: settings.plugins.Octoslack.supported_events." + internalName + ".SlackMinSnapshotUpdateInterval'" : "")
                 + ">");
            eventHtml.push("            <div class='octoslack_label octoslack_action_label'>Snapshot Upload Minimum Interval</div>");
            eventHtml.push("            <br/>");
            eventHtml.push("            <br/>");
            eventHtml.push("            <small class='muted'>");
            eventHtml.push("                For Slack snapshot uploads, the minumum amount of time (in minutes) that must pass before the next progress snapshot is uploaded. Requires Slack API Token. 0 = disabled (always send snapshots)");
            eventHtml.push("            </small>");
            eventHtml.push("        <br/>");
            eventHtml.push("        </div>");
            eventHtml.push("        <div class='octoprint_config_row'>");
                //IntervalPct
	        eventHtml.push("        <div class='octoprint_config_row'>");
	        eventHtml.push("            <input type='number' step='any' min='0' max='99' class='input-mini text-right' id='octoslack_event_" + internalName + "_InvervalPct' "
                    + (useDataBind ? "data-bind='value: settings.plugins.Octoslack.supported_events." + internalName + ".IntervalPct'" : "")
                    + ">");
	        eventHtml.push("            <div class='octoslack_label octoslack_action_label'>Interval - Percentage</div>");
	        eventHtml.push("            <br/>");
	        eventHtml.push("            <small class='muted'>");
	        eventHtml.push("                0 = disabled");
	        eventHtml.push("                <br/>");
	        eventHtml.push("                A value of 5 would indicate report progress should be sent at 5%, 10%, 15%, etc.");
	        eventHtml.push("            </small>");
	        eventHtml.push("        </div>");
	        eventHtml.push("        <br/>");

                //IntervalHeight
	        eventHtml.push("        <div class='octoprint_config_row'>");
	        eventHtml.push("            <input type='number' step='0.1' min='0' max='10000' class='input-mini text-right' id='octoslack_event_" + internalName + "_InvervalHeight' "
                    + (useDataBind ? "data-bind='value: settings.plugins.Octoslack.supported_events." + internalName + ".IntervalHeight'" : "")
                    + ">");
	        eventHtml.push("            <div class='octoslack_label octoslack_action_label'>Interval - Height (mm)</div>");
	        eventHtml.push("            <br/>");
	        eventHtml.push("            <small class='muted'>");
	        eventHtml.push("                0 = disabled");
	        eventHtml.push("                <br/>");
	        eventHtml.push("                A value of 50 would indicate report progress should be sent each time the nozzle height has raised an additional 50mm");
	        eventHtml.push("            </small>");
	        eventHtml.push("        </div>");
	        eventHtml.push("        <br/>");


                //IntervalTime
	        eventHtml.push("        <div class='octoprint_config_row'>");
	        eventHtml.push("            <input type='number' step='any' min='0' class='input-mini text-right' id='octoslack_event_" + internalName + "_IntervalTime' "
                    + (useDataBind ? "data-bind='value: settings.plugins.Octoslack.supported_events." + internalName + ".IntervalTime'" : "")
                    + ">");
	        eventHtml.push("            <div class='octoslack_label octoslack_action_label'>Interval - Time (minutes)</div>");
	        eventHtml.push("            <br/>")
	        eventHtml.push("            <small class='muted'>");
	        eventHtml.push("                0 = disabled");
	        eventHtml.push("                <br/>");
	        eventHtml.push("                A value of 5 would indicate report progress should be sent every 5 minutes ");
	        eventHtml.push("            </small>");
	        eventHtml.push("        </div>");
	        eventHtml.push("        <br/>");
            }

            if(eventType == "STANDARD" && internalName == "Heartbeat") {
                //IntervalTime
	        eventHtml.push("        <div class='octoprint_config_row'>");
	        eventHtml.push("            <input type='number' step='any' min='1' class='input-mini text-right' id='octoslack_event_" + internalName + "_IntervalTime' "
                    + (useDataBind ? "data-bind='value: settings.plugins.Octoslack.supported_events." + internalName + ".IntervalTime'" : "")
                    + ">");
	        eventHtml.push("            <div class='octoslack_label octoslack_action_label'>Interval - Time (minutes)</div>");
	        eventHtml.push("            <br/>")
	        eventHtml.push("            <small class='muted'>");
	        eventHtml.push("                0 = disabled");
	        eventHtml.push("                <br/>");
	        eventHtml.push("                A value of 5 would indicate a heartbeat message should be sent every 5 minutes ");
	        eventHtml.push("            </small>");
	        eventHtml.push("        </div>");
	        eventHtml.push("        <br/>");
            }

            //ChannelOverride
	    eventHtml.push("        <div class='octoprint_config_row'>");
	    eventHtml.push("            <input type='text' size='30' id='octoslack_event_" + internalName + "_ChannelOverride' "
                + (useDataBind ? "data-bind='value: settings.plugins.Octoslack.supported_events." + internalName + ".ChannelOverride'" : "")
                + (customChannelOverride.trim().length > 0 ? "value='" + this.escapeHtml(customChannelOverride.trim()) + "'" : "")
                + ">");
	    eventHtml.push("            <div class='octoslack_label octoslack_action_label'>Channel(s) override</div>");
	    eventHtml.push("        </div>");

            //CaptureSnapshot
	    eventHtml.push("        <div class='octoprint_config_row'>");
	    eventHtml.push("            <input type='checkbox' class='octoslack_valign octoslack_checkbox_margin_override' id='octoslack_event_" + internalName + "_snapshot' "
                + (useDataBind ? "data-bind='checked: settings.plugins.Octoslack.supported_events." + internalName + ".CaptureSnapshot'" : "")
                + (customCaptureSnapshot ? " checked " : " ")
                + ">");
	    eventHtml.push("            <div class='octoslack_label octoslack_action_label' onclick=\"$('#octoslack_event_" + internalName + "_snapshot').trigger('click')\">Include snapshot</div>");
	    eventHtml.push("        </div>");

            if(eventType == "STANDARD" && internalName == "MovieDone") {
                //UploadMovie
	        eventHtml.push("        <div class='octoprint_config_row' octoslack_timelapse_upload>");
	        eventHtml.push("            <input type='checkbox' class='octoslack_valign octoslack_checkbox_margin_override' id='octoslack_event_" + internalName + "_uploadmovie' "
                    + (useDataBind ? "data-bind='checked: settings.plugins.Octoslack.supported_events." + internalName + ".UploadMovie'" : "")
                    + ">");
	        eventHtml.push("            <div class='octoslack_label octoslack_action_label' onclick=\"$('#octoslack_event_" + internalName + "_uploadmovie').trigger('click')\">Upload timelapse</div>");
	        eventHtml.push("            <br/>")
	        eventHtml.push("            <small class='muted'>");
	        eventHtml.push("                Upload rendered timelapse movie via the configured Snapshot Hosting option. Enabling this option will delay publishing of this event to Slack until after the timelapse has been uploaded.");
	        eventHtml.push("            </small>");
	        eventHtml.push("        </div>");

                //UploadedMovieLink
	        eventHtml.push("        <div class='octoprint_config_row' octoslack_timelapse_upload>");
	        eventHtml.push("            <input type='checkbox' class='octoslack_valign octoslack_checkbox_margin_override' id='octoslack_event_" + internalName + "_uploadmovielink' "
                    + (useDataBind ? "data-bind='checked: settings.plugins.Octoslack.supported_events." + internalName + ".UploadMovieLink'" : "")
                    + ">");
	        eventHtml.push("            <div class='octoslack_label octoslack_action_label' onclick=\"$('#octoslack_event_" + internalName + "_uploadmovielink').trigger('click')\">Include uploaded timelapse URL</div>");
	        eventHtml.push("            <br/>")
	        eventHtml.push("            <br/>")
	        eventHtml.push("            <small class='muted'>");
	        eventHtml.push("                If a timelapse movie has been uploaded, include its download link in the event message");
	        eventHtml.push("            </small>");
	        eventHtml.push("        </div>");
            }

            //Message
	    eventHtml.push("        <div class='octoprint_config_row'>");
	    eventHtml.push("            <textarea class='octoslack_width_auto' rows='2' cols='60' id='octoslack_event_" + internalName + "_message' "
                + (useDataBind ? "data-bind='value: settings.plugins.Octoslack.supported_events." + internalName + ".Message'" : "")
                + ">"
                + (customMessage.trim().length > 0 ? this.escapeHtml(customMessage.trim()) : "")
                + "</textarea>");
	    eventHtml.push("            <div class='octoslack_label octoslack_action_label'>Message</div>");
	    eventHtml.push("        </div>");

	    //Fallback
	    eventHtml.push("        <div class='octoprint_config_row' octoslack_msg_slack>");
	    eventHtml.push("            <textarea class='octoslack_width_auto' rows='2' cols='60' id='octoslack_event_" + internalName + "_fallback' " 
                + (useDataBind ? "data-bind='textInput: settings.plugins.Octoslack.supported_events." + internalName + ".Fallback'" : "")
                + ">"
	        + (customFallback.trim().length > 0 ? this.escapeHtml(customFallback.trim()) : "")
	        + "</textarea>");
	    eventHtml.push("            <div class='octoslack_label octoslack_action_label'>Fallback</div>");
	    eventHtml.push("        </div>");

            //PushoverSound
	    eventHtml.push("        <div class='octoprint_config_row' octoslack_msg_pushover>");
            eventHtml.push("            <select class='octoslack_select' id='octoslack_event_" + internalName + "_PushoverSound' "
                 + (useDataBind ? "data-bind='value: settings.plugins.Octoslack.supported_events." + internalName + ".PushoverSound'" : "")
                 + ">");

            var pushoversounds_len = pushoversounds.length;
            for (var sounds_idx = 0; sounds_idx < pushoversounds_len; sounds_idx++) {
                var sound_arr = pushoversounds[sounds_idx];
                var sound_var = sound_arr[0].trim();
                var sound_name = sound_arr[1].trim();

                eventHtml.push("                <option value='");
                eventHtml.push(sound_var);
		eventHtml.push("' " + (useDataBind ? "" : (customPushoverSound == sound_var || (sound_var == "pushover" && customPushoverSound == '') ? "selected" : "")));
                eventHtml.push(">" + sound_name + "</option>");
	    }

            eventHtml.push("            </select>");
	    eventHtml.push("            <div class='octoslack_label octoslack_action_label'>Pushover Sound</div>");
	    eventHtml.push("        </div>");

            //PushoverPriority
	    eventHtml.push("        <div class='octoprint_config_row' octoslack_msg_pushover>");
            eventHtml.push("            <select class='octoslack_select' id='octoslack_event_" + internalName + "_PushoverPriority' "
                 + (useDataBind ? "data-bind='value: settings.plugins.Octoslack.supported_events." + internalName + ".PushoverPriority'" : "")
                 + ">");

            var pushoverpriorities_len = pushoverpriorities.length;
            for (var priorities_idx = 0; priorities_idx < pushoverpriorities_len; priorities_idx++) {
                var priority_arr = pushoverpriorities[priorities_idx];
                var priority_var = priority_arr[0].trim();
                var priority_name = priority_arr[1].trim();

                eventHtml.push("                <option value='");
                eventHtml.push(priority_var);
		eventHtml.push("' " + (useDataBind ? "" : (customPushoverPriority == priority_var || (priority_var == "0" && customPushoverPriority == '') ? "selected" : "")));
                eventHtml.push(">" + priority_name + "</option>");
	    }

            eventHtml.push("            </select>");
	    eventHtml.push("            <div class='octoslack_label octoslack_action_label'>Pushover Priority</div>");
	    eventHtml.push("        </div>");


            if(action_text != null && action_handler != null)
                eventHtml.push("        <div class='octoslack_align_right' style='width: 100%;'><button onclick='" + action_handler + "'>" + this.escapeHtml(action_text) + "</button></div>");
	    eventHtml.push("        </div>");
	}

        return eventHtml.join("\n");
    },

    buildSnapshotURLsTable : function() {
	var hidden_value = $("#octoslack_snapshot_urls_hidden").val();
	var snapshot_urls = hidden_value.split(",");

        var urlsTable = "<table id='snapshot_urls_table'>";
        for (var i = 0; i < snapshot_urls.length; i++) {
	    var decoded = decodeURIComponent(snapshot_urls[i]);
	    var parts = decoded.split('|');
	    var snapshotUrl = parts[0];
	    var snapshotFlipH = false;
	    var snapshotFlipV = false;
	    var snapshotRotate90 = false;
	    if(parts.length == 4) {
                snapshotFlipH = parts[1] === 'true';
		snapshotFlipV = parts[2] === 'true';
		snapshotRotate90 = parts[3] === 'true';
            }
            var urlRow = this.createURLRowHTML(snapshotUrl, snapshotFlipH, snapshotFlipV, snapshotRotate90,
                "Remove", "Octoslack.removeURLRow(event, this); return false;");
            urlsTable += urlRow;
        }

        var addRow = this.createURLRowHTML(null, false, false, false, "Add URL", "Octoslack.addBlankURLRow(event, this); return false;");
        urlsTable += addRow;

        urlsTable += "</table>";

        var urls_container = $("#octoslack_snapshot_urls_container");
        urls_container.attr("class", "octoslack_visible");
        urls_container.html(urlsTable);
    },

    addBlankURLRow : function(e, cell_elem) {
        var buttonElem = cell_elem.parentNode;
        var rowElem = buttonElem.parentNode;
        var tableElem = rowElem.parentNode;

        var newRow = document.createElement('tr');
        tableElem.insertBefore(newRow, rowElem);

        newRow.outerHTML = this.createURLRowHTML("", false, false, false, "Remove", "Octoslack.removeURLRow(event, this); return false;");
    },

    createURLRowHTML : function(url, flipH, flipV, rotate90, action_text, action_handler) {
        var tableRow = "<tr>";
        tableRow += "<td class='octoslack_row_bottom_padding'>";

        //TODO we're lazily updating the list on every change (quick and dirty solution)
        if(url == null) {
            tableRow += "&nbsp;";
	}
        else {
            tableRow += "<input type='text' class='octoslack_width_auto' size='60' oninput='Octoslack.storeSnapshotURLs();' onchange='Octoslack.storeSnapshotURLs();' value='" + this.escapeHtml(url) + "'>";
            tableRow += "<br/>";

	    tableRow += "<input type='checkbox' class='octoslack_checkbox_margin_override' "
		+ " oninput='Octoslack.storeSnapshotURLs();' onchange='Octoslack.storeSnapshotURLs();' "
                + (flipH ? " checked " : " ")
                + ">Flip horizontally</input>";

            tableRow += "&nbsp;&nbsp;"

	    tableRow += "<input type='checkbox' class='octoslack_checkbox_margin_override' "
		+ " oninput='Octoslack.storeSnapshotURLs();' onchange='Octoslack.storeSnapshotURLs();' "
                + (flipV ? " checked " : " ")
                + ">Flip vertically</input>";

            tableRow += "&nbsp;&nbsp;"

	    tableRow += "<input type='checkbox' class='octoslack_checkbox_margin_override' "
		+ " oninput='Octoslack.storeSnapshotURLs();' onchange='Octoslack.storeSnapshotURLs();' "
                + (rotate90 ? " checked " : " ")
                + ">Rotate 90 degrees counter clockwise</input>";
	}
        tableRow += "</td>";
        tableRow += "<td valign='top' style='width: 100px;' class='octoslack_row_bottom_padding'><button onclick='" + action_handler + "'>" + this.escapeHtml(action_text) + "</button></td>";
        tableRow += "</tr>";

        return tableRow;
    },

    removeURLRow : function(e, cell_elem) {
        var buttonElem = cell_elem.parentNode;
        var rowElem = buttonElem.parentNode;
        rowElem.parentNode.removeChild(rowElem);

        this.storeSnapshotURLs();
    },

    storeSnapshotURLs : function() {

        var urls = [];

        var urlsTable = $("#snapshot_urls_table")[0];

        for (var i = 0, row; row = urlsTable.rows[i]; i++) {
            var cell = row.cells[0];

	    var snapshotUrl = null;
	    var snapshotFlipH = false;
	    var snapshotFlipV = false;
	    var snapshotRotate90 = false;

	    for (var j = 0, childElem; childElem = cell.children[j]; j++) {
		var nodename = childElem.nodeName.toLowerCase();
                if(j == 0 && nodename == "input") {
	            snapshotUrl = childElem.value;
		} else if(j == 2 && nodename == "input") {
                    snapshotFlipH = childElem.checked;
		} else if(j == 3 && nodename == "input") {
                    snapshotFlipV = childElem.checked;
		} else if(j == 4 && nodename == "input") {
                    snapshotRotate90 = childElem.checked;
		}
	    }

	    if(snapshotUrl == null || snapshotUrl.trim().length == 0)
	        continue;

	    var combinedstr = snapshotUrl + "|" + snapshotFlipH + "|" + snapshotFlipV + "|" + snapshotRotate90;
	    urls.push(encodeURIComponent(combinedstr));
        }

	var combined_str = urls.join(",");


	var urls_hidden = $("#octoslack_snapshot_urls_hidden");

	urls_hidden.val(combined_str);
        urls_hidden.trigger('change');
    },

    buildGcodeEventsTable : function() {
	var hidden_value = $("#octoslack_gcode_events_hidden").val();
	var gcode_events = hidden_value == undefined || hidden_value.trim().length == 0 ? [] : eval(hidden_value);

	var eventsHtml = this.buildOctoPrintEventConfigRow('GCODE', gcode_events, "Remove", "Octoslack.removeGcodeEventRow(event, this); return false;");
        
        var gcode_events_container = $("#octoslack_gcode_events_container");
        gcode_events_container.html(eventsHtml);
    },

    addGcodeEventRow : function(e) {
        var gcode_events_container = $("#octoslack_gcode_events_container");

	var empty_event = [
		{ "InternalName" : String(Date.now()), 
                  "GcodeType" : "sent", 
                  "Gcode" : "", 
                  "Color" : "good", 
                  "Enabled" : true, 
                  "ChannelOverride" : "", 
                  "CaptureSnapshot" : true, 
                  "Message" : "", 
                  "Fallback" : "",
                  "PushoverSound" : "",
                  "PushoverPriority" : ""
                },
	];

        var new_event_html = this.buildOctoPrintEventConfigRow('GCODE', empty_event, "Remove", "Octoslack.removeGcodeEventRow(event, this); return false");
        gcode_events_container.append(new_event_html);

        this.changeConnectionType();
    },

    createGcodeEventRowHTML : function(url, action_text, action_handler) {
        var tableRow = "<tr>";
        tableRow += "<td>";

        //TODO we're lazily updating the list on every change (quick and dirty solution)
        if(url == null)
            tableRow += "&nbsp;";
        else
            tableRow += "<input type='text' class='octoslack_width_auto' size='60' oninput='Octoslack.storeSnapshotURLs();' onchange='Octoslack.storeSnapshotURLs();' value='" + this.escapeHtml(url) + "'>";
        tableRow += "</td>";
        tableRow += "<td style='width: 100px;'><button onclick='" + action_handler + "'>" + this.escapeHtml(action_text) + "</button></td>";
        tableRow += "</tr>";

        return tableRow;
    },

    removeGcodeEventRow : function(e, cell_elem) {
        var buttonElem = cell_elem.parentNode;
        var rowElem = buttonElem.parentNode;
        rowElem.parentNode.removeChild(rowElem);
    },

    storeGcodeEvents : function() {

        var gcode_events = [];

        var gcode_events_container = $("#octoslack_gcode_events_container");

        gcode_events_container.children().each(function() {
            var id = this.getAttribute('id')
            if(!id.startsWith("GCODE_"))
                return;

            var internalName = this.getAttribute('internalname');
            if(internalName == undefined)
                return;

            var enabled = $("#octoslack_event_" + internalName + "_enabled").is(':checked');
            var gcode = $("#octoslack_event_" + internalName + "_gcode").val();
            var gcodematchtype = $("#octoslack_event_" + internalName + "_gcode_match_type").val();
            var gcodetype = $("#octoslack_event_" + internalName + "_gcode_type").val();
            var color = $("#octoslack_event_" + internalName + "_color").val();
            var channeloverride = $("#octoslack_event_" + internalName + "_ChannelOverride").val();
            var snapshot = $("#octoslack_event_" + internalName + "_snapshot").is(':checked');
            var message = $("#octoslack_event_" + internalName + "_message").val();
            var fallback = $("#octoslack_event_" + internalName + "_fallback").val();
            var pushoverSound = $("#octoslack_event_" + internalName + "_PushoverSound").val().trim();
            var pushoverPriority = $("#octoslack_event_" + internalName + "_PushoverPriority").val().trim();
	
            gcode_events.push({ "InternalName" : internalName, 
                                  "Gcode" : gcode, 
                                  "GcodeMatchType" : gcodematchtype, 
                                  "GcodeType" : gcodetype, 
                                  "Color" : color, 
                                  "Enabled" : enabled, 
                                  "ChannelOverride" : channeloverride, 
                                  "CaptureSnapshot" : snapshot, 
                                  "Message" : message, 
                                  "Fallback" : fallback,
                                  "PushoverSound" : pushoverSound,
                                  "PushoverPriority" : pushoverPriority,
                                });
        });

        var combined_str = JSON.stringify(gcode_events);

	var hidden_value = $("#octoslack_gcode_events_hidden");
        hidden_value.val(combined_str);
        hidden_value.trigger('change');
    },
}

window.Octoslack = Octoslack;
