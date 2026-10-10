# -*- coding: utf-8 -*-
"""Textual CSS styles for the Terminal User Interface."""

TUI_CSS = """
Screen {
    background: #202020;
    color: #F3F3F3;
}

#top_bar {
    height: 3;
    background: #2C2C2C;
    border-bottom: solid #383838;
    padding: 0 1;
}

#app_title {
    width: 18;
    text-style: bold;
    color: #4CC2FF;
    content-align: left middle;
}

.toggle_nav_btn {
    width: 8;
    min-width: 8;
    height: 3;
    margin-right: 1;
    background: #333333;
    color: #E0E0E0;
    border: none;
}

.toggle_nav_btn:hover {
    background: #444444;
}

#search_box {
    width: 1fr;
    max-width: 28;
    margin-right: 1;
}

#main_container {
    height: 1fr;
}

#nav_tree {
    width: 24;
    background: #262626;
    border-right: solid #383838;
}

#content_area {
    width: 1fr;
    height: 1fr;
    padding: 0 1;
    overflow-y: auto;
}

#op_header {
    height: auto;
    margin-bottom: 1;
}

#op_title {
    text-style: bold;
    color: #FFFFFF;
}

#op_desc {
    color: #A0A0A0;
    margin-bottom: 1;
}

#destructive_banner {
    background: #3D1418;
    color: #FF7B72;
    border: solid #FF7B72;
    padding: 0 1;
    margin-bottom: 1;
    text-style: bold;
}

#form_container {
    height: auto;
    max-height: 12;
    background: #282828;
    border: solid #383838;
    padding: 1;
    margin-bottom: 1;
    overflow-y: auto;
}

.field_row {
    height: auto;
    margin-bottom: 1;
}

.field_label {
    text-style: bold;
    color: #E0E0E0;
    margin-bottom: 0;
}

.field_help {
    color: #888888;
}

.path_row {
    height: auto;
    margin-bottom: 0;
}

.path_input {
    width: 1fr;
}

.btn_browse {
    width: 10;
    margin-left: 1;
}

#actions_bar {
    height: 3;
    margin-bottom: 1;
}

#btn_run {
    background: #0067C0;
    color: #FFFFFF;
    text-style: bold;
    margin-right: 1;
}

#btn_run:hover {
    background: #1979C9;
}

#btn_reset {
    margin-right: 1;
}

#lbl_status {
    color: #A0A0A0;
    margin-left: 1;
    content-align: left middle;
}

#exec_panel {
    height: auto;
    background: #242424;
    border: solid #383838;
    padding: 1;
    margin-bottom: 1;
}

#progress_bar {
    margin-bottom: 1;
}

#log_view {
    height: 5;
    background: #1A1A1A;
    border: solid #333333;
}

#result_panel {
    height: 1fr;
    background: #282828;
    border: solid #383838;
    padding: 1;
    overflow-y: auto;
}

.result_success {
    color: #56D364;
    text-style: bold;
    margin-bottom: 1;
}

.result_failure {
    color: #FF7B72;
    text-style: bold;
    margin-bottom: 1;
}

/* Modal Dialogs */
#modal_dialog {
    width: 68;
    max-width: 90%;
    height: auto;
    max-height: 20;
    background: #2C2C2C;
    border: thick #0067C0;
    padding: 1 2;
}

#modal_title {
    text-style: bold;
    color: #4CC2FF;
    margin-bottom: 1;
}

#modal_message {
    margin-bottom: 1;
}

#modal_fields {
    height: auto;
    max-height: 8;
    margin-bottom: 1;
    overflow-y: auto;
}

#modal_actions {
    height: 3;
    align-horizontal: right;
}

#modal_actions Button {
    margin-left: 1;
}

/* Path Browser */
#browser_dialog {
    width: 72;
    max-width: 95%;
    height: 22;
    background: #2C2C2C;
    border: thick #0067C0;
    padding: 1 2;
}

#browser_dialog DirectoryTree {
    height: 1fr;
    background: #242424;
    border: solid #383838;
    margin: 1 0;
}
"""
