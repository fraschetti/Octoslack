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
                Octoslack.beforeBindingInit();
        };

        self.onAfterBinding = function() {
                Octoslack.afterBindingInit();
        };

	self.onEventSettingsUpdated  = function() {
		Octoslack.afterSettingsSaved();
	};
    }

    // view model class, parameters for constructor, container to bind to
    OCTOPRINT_VIEWMODELS.push([
        OctoslackViewModel, ["settingsViewModel"], [ ]
    ]);
});

var Octoslack = {

    beforeBindingInit : function() {
	this.buildOctoPrintEventConfigs();
    },

    last_connection_method : null,
    last_bot_commands : null,

    afterBindingInit : function() {
        this.setInitialInputStates();
        this.buildSnapshotURLsTable();
	this.applyMattermostChanges();

	this.last_connection_method = $("#octoslack_connection_method_hidden").val();
	this.last_bot_commands = $("#octoslack_bot_commands").is(":checked");

        this.changeImgurClientID();
        $("#octoslack_imgur_refresh_token").bind('input propertychange', function() { Octoslack.changeImgurRefreshToken(); });
        $("#octoslack_imgur_album_id").bind('input propertychange', function() { Octoslack.changeImgurAlbumID(); });
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

    afterSettingsSaved : function() {
	
	var new_connection_method = $("#octoslack_connection_method_hidden").val();
	var new_channel = $("#octoslack_channel").val();

	if(new_connection_method == "APITOKEN" && new_channel.trim().length ==0) {
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

	if(this.last_connection_method == "APITOKEN" && (this.last_bot_commands != new_bot_commands))
		restart_needed = true;
	else if(this.last_connection_method == "APITOKEN" && new_connection_method != "APITOKEN" && this.last_bot_commands)
		restart_needed = true;
	else if(this.last_connection_method != "APITOKEN" && new_connection_method == "APITOKEN" && new_bot_commands)
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

    changeConnectionType : function(new_type) {
        var mattermost_enabled = $("#octoslack_mattermost_compatabilty_mode").is(":checked");
	if(mattermost_enabled)
		new_type = "WEBHOOK";
        var mattermost_enabled = $("#octoslack_mattermost_compatabilty_mode").is(":checked");

        var apiTokenGroup = $("#octoslack_apitoken_group");
        var webhookGroup = $("#octolack_webhook_group");

        apiTokenGroup.attr("class", "octoslack_hidden");
        webhookGroup.attr("class", "octoslack_hidden");

        switch (new_type) {
            case "APITOKEN":
                apiTokenGroup.attr("class", "octoslack_visible");
                break;
           case "WEBHOOK":
                 webhookGroup.attr("class", "octoslack_visible");
                   break;
        }

        var connection_method_hidden = $("#octoslack_connection_method_hidden");
        connection_method_hidden.val(new_type);
        connection_method_hidden.trigger('change');
    },

    toggleUseSlackIdentity : function(checkbox) {
        var checked = checkbox.checked;
        var custom_identity_div = $("#octoslack_custom_identity_group");

        custom_identity_div.attr("class", checked ? "octoslack_hidden" : "octoslack_visible");
    },

    changeSnapshotUploadMethod : function(selection) {
        var imgurGroup = $("#octoslack_imgur_group");
        var s3Group = $("#octolack_s3_group");

        imgurGroup.attr("class", "octoslack_hidden");
        s3Group.attr("class", "octoslack_hidden");

        switch (selection.value) {
            case "IMGUR":
                imgurGroup.attr("class", "octoslack_visible");
                break;
            case "S3":
                s3Group.attr("class", "octoslack_visible");
                break;
        }

        var upload_method = $("#octoslack_upload_method_hidden");
        upload_method.val(selection.value);
        upload_method.trigger('change');
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
		[ "PrintStarted", "Print started" ],
		[ "PrintFailed", "Print failed" ],
		[ "PrintCancelled", "Print cancelled" ],
		[ "PrintPaused", "Print paused" ],
		[ "PrintResumed", "Print resumed" ],
		[ "PrintDone", "Print finished" ],
		[ "Progress", "Print progress" ],
		[ "MovieRendering", "Timelapse render started" ],
		[ "MovieDone", "Timelapse render finished" ],
		[ "MovieFailed", "Timelapse render failed" ],
		[ "Error", "OctoPrint error" ],
		[ "Startup", "OctoPrint started" ],
		[ "Shutdown", "OctoPrint stopped" ],
		[ "Connecting", "Printer connecting" ],
		[ "Connected", "Printer connected" ],
		[ "Disconnecting", "Printer disconnecting" ],
		[ "Disconnected", "Printer disconnected" ],
	];

	var eventHtml = [];

	for(var i = 0; i < events.length; i++) {
	    var event = events[i];
	    var internalName = event[0];
	    var displayName = event[1];

	    eventHtml.push("        <h3>" + this.escapeHtml(displayName) + "</h3>");
            
            //Enabled
	    eventHtml.push("        <div class='octoprint_config_row'>");
	    eventHtml.push("            <input type='checkbox' class='octoslack_valign' id='octoslack_event_" + internalName + "_enabled' data-bind='checked: settings.plugins.Octoslack.supported_events." + internalName + ".Enabled'>");
	    eventHtml.push("            <div class='octoslack_label octoslack_action_label' onclick=\"$('#octoslack_event_" + internalName + "_enabled').trigger('click')\">Enabled</div>");
	    eventHtml.push("        </div>");


            //CaptureSnapshot
	    eventHtml.push("        <div class='octoprint_config_row'>");
	    eventHtml.push("            <input type='checkbox' class='octoslack_valign' id='octoslack_event_" + internalName + "_snapshot' data-bind='checked: settings.plugins.Octoslack.supported_events." + internalName + ".CaptureSnapshot'>");
	    eventHtml.push("            <div class='octoslack_label octoslack_action_label' onclick=\"$('#octoslack_event_" + internalName + "_snapshot').trigger('click')\">Include snapshot</div>");
	    eventHtml.push("        </div>");

            //Message
	    eventHtml.push("        <div class='octoprint_config_row'>");
	    eventHtml.push("            <textarea class='octoslack_width_auto' rows='2' cols='60' id='octoslack_event_" + internalName + "_message' data-bind='value: settings.plugins.Octoslack.supported_events." + internalName + ".Message'></textarea>");
	    eventHtml.push("            <div class='octoslack_label octoslack_action_label' onclick=\"$('#octoslack_event_" + internalName + "_message').trigger('click')\">Message</div>");
	    eventHtml.push("        </div>");


            //Fallback
	    eventHtml.push("        <div class='octoprint_config_row'>");
	    eventHtml.push("            <textarea class='octoslack_width_auto' rows='2' cols='60' id='octoslack_event_" + internalName + "_fallback' data-bind='textInput: settings.plugins.Octoslack.supported_events." + internalName + ".Fallback'></textarea>");
	    eventHtml.push("            <div class='octoslack_label octoslack_action_label' onclick=\"$('#octoslack_event_" + internalName + "_fallback').trigger('click')\">Fallback</div>");
	    eventHtml.push("        </div>");
	}

	var combined_str = eventHtml.join("\n");

        var events_container = $("#octoslack_events_container");
        events_container.attr("class", "octoslack_visible");
        events_container.html(combined_str);
    },

    buildSnapshotURLsTable : function() {
	var hidden_value = $("#octoslack_snapshot_urls_hidden").val();
	var snapshot_urls = hidden_value.split(",");

        var urlsTable = "<table id='snapshot_urls_table'>";
        for (var i = 0; i < snapshot_urls.length; i++) {
	    var decoded = decodeURIComponent(snapshot_urls[i]);
            var urlRow = this.createURLRowHTML(decoded, "Remove", "Octoslack.removeURLRow(event, this); return false");
            urlsTable += urlRow;
        }

        var addRow = this.createURLRowHTML(null, "Add", "Octoslack.addBlankURLRow(event, this); return false");
        urlsTable += addRow;

        urlsTable += "</table>";

        var urls_container = $("#octoslack_snapshot_urls_container");
        urls_container.attr("class", "octoslack_visible");
        urls_container.html(urlsTable);
    },

    addBlankURLRow : function(e, cell_elem) {
        var rowElem = cell_elem.parentNode;
        var tableElem = rowElem.parentNode;

        var newRow = document.createElement('tr');
        tableElem.insertBefore(newRow, rowElem);

        newRow.outerHTML = this.createURLRowHTML("", "Remove", "Octoslack.removeURLRow(event, this); return false");
    },

    createURLRowHTML : function(url, action_text, action_handler) {
        var tableRow = "<tr>";
        tableRow += "<td>";

        //TODO we're lazily updating the list on every change (quick and dirty solution)
        if(url == null)
            tableRow += "&nbsp;";
        else
            tableRow += "<input type='text' class='octoslack_width_auto' size='60' oninput='Octoslack.storeSnapshotURLs();' onchange='Octoslack.storeSnapshotURLs();' value='" + this.escapeHtml(url) + "'>";
        tableRow += "</td>";
        tableRow += "<td class='octoslack_action_label' style='width: 100px;' onclick='" + action_handler + "'><button>" + this.escapeHtml(action_text) + "</button></td>";
        tableRow += "</tr>";

        return tableRow;
    },

    removeURLRow : function(e, cell_elem) {
        var rowElem = cell_elem.parentNode;
        rowElem.parentNode.removeChild(rowElem);

        this.storeSnapshotURLs();
    },

    storeSnapshotURLs : function() {
        var urls = [];

        var urlsTable = $("#snapshot_urls_table")[0];

        for (var i = 0, row; row = urlsTable.rows[i]; i++) {
            var cell = row.cells[0];
            var input = cell.firstChild;
            if(input == null)
		continue;

            if(input.nodeName.toLowerCase() == "input") {
                var url = input.value;
                if(url == null) continue;

                url = url.trim();
                if(url.length > 0)
                    urls.push(encodeURIComponent(url));
            }
        }

	var combined_str = urls.join(",");


	var urls_hidden = $("#octoslack_snapshot_urls_hidden");

	urls_hidden.val(combined_str);
        urls_hidden.trigger('change');
    },
}
