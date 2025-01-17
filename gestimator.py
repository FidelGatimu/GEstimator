#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# run.py
#  
#  Copyright 2014 Manu Varkey <manuvarkey@gmail.com>
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
 

import sys, os, io, logging, appdirs

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GObject

# Get logger object
log = logging.getLogger()

from estimator import MainApp, misc

if __name__ == '__main__':
    # Setup logging
    
    # Setup Logging to temporary file
    log_file_temp = io.StringIO()
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        stream=log_file_temp,level=logging.INFO)
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        stream=sys.stdout,level=logging.INFO)
    # Logging to stdout
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    log.addHandler(ch)
    # Log all uncaught exceptions
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        log.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    sys.excepthook = handle_exception
    
    # Initialise main window
    
    log.info('Start Program Execution')
    app = MainApp()
    log.info('Entering Gtk main loop')
    app.run(sys.argv)
    log.info('End Program Execution')
    
    # Copy temporary logfile to log folder
    dirs = appdirs.AppDirs(misc.PROGRAM_NAME, misc.PROGRAM_AUTHOR, version=misc.PROGRAM_VER)
    log_dir = misc.posix_path(dirs.user_data_dir, 'logs')
    log_file = misc.posix_path(log_dir, misc.PROGRAM_NAME + '.log')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    with open(log_file, 'w') as fobj:
        fobj.write(log_file_temp.getvalue())
    
    
