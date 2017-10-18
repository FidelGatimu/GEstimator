#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  analysis.py
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
#  

import pickle, codecs, os.path, copy, logging
from collections import OrderedDict
from decimal import Decimal, ROUND_HALF_UP

# Rates rounding function
def Currency(x):
    return Decimal(x).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)

from gi.repository import Gtk, Gdk, GLib

# local files import
from .. import misc, data, undo
from ..undo import undoable

# Setup logger object
log = logging.getLogger(__name__)


class ResourceView:
    """Implement resource view"""
        
    def __init__(self, parent, database, box, compact=False, read_only=False):
        """Setup resource view and connect signals
        
            Arguments:
                parent: Parent window
                database: database of items to be displayed
                box: Box to implement resource view
        """
        log.info('ResourceView - Initialise')
        
        # Passed data
        self.parent = parent
        self.database = database
        self.read_only = read_only
        self.box = box
        
        # Additional data
        captions = ['Code', 'Description', 'Unit', 'Rate', 'Tax',
                    'Discount', 'Reference']
        expands = [False, True, False, False, False, False, False]
        if compact:
            widths = [150, 300, 80, 80, 80, 80, 50]
        else:
            widths = [150, 400, 80, 80, 80, 80, 200]            
        columntypes = [str, str, str, float, float, float, str]
        
        # Setup treestore and filter
        self.store = Gtk.TreeStore(*([str]*7+[bool]*7))
        self.filter = self.store.filter_new()
        self.filter.set_visible_func(self.filter_func, data=[0,1])

        self.search_field = Gtk.SearchEntry()
        self.search_field.set_width_chars(30)
        self.search_bar = Gtk.SearchBar()
        self.search_bar.set_show_close_button(True)
        scrolled = Gtk.ScrolledWindow()
        self.tree = Gtk.TreeView(self.filter)
        # Pack widgets
        self.search_bar.add(self.search_field)
        self.box.pack_start(self.search_bar, False, False, 0)
        self.box.pack_start(scrolled, True, True, 0)
        scrolled.add(self.tree)
        
        # Setup tree view
        self.tree.set_grid_lines(3)
        self.tree.set_enable_tree_lines(True)
        self.tree.set_search_equal_func(self.equal_func, [0,1,2])
        self.tree.set_show_expanders(False)
        self.tree.set_level_indentation(30)
        self.tree.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.tree.set_rubber_banding(True)
        self.tree.connect("key-press-event", self.on_key_press_treeview)
        self.tree.connect("button-press-event", self.on_click_event)
        self.search_field.connect("search-changed", self.on_search)
        
        self.columns = dict()
        self.cells = dict()
        for slno, [caption, expand, width, columntype] in enumerate(zip(captions, expands, widths, columntypes)):
            column = Gtk.TreeViewColumn(caption)
            cell = Gtk.CellRendererText()
            self.tree.append_column(column)
            self.columns[caption] = column
            self.cells[caption] = cell
            column.pack_start(cell, expand)
            column.add_attribute(cell, "text", slno)
            column.set_fixed_width(width)
            column.set_resizable(True)
            
            if not read_only:
                column.add_attribute(cell, "editable", 7+slno)
                
            if columntype is str:
                cell.connect("edited", self.on_cell_edited_text, slno)
                cell.connect("editing_started", self.on_cell_edit_started, slno)
            elif columntype is float:
                cell.connect("edited", self.on_cell_edited_num, slno)
                cell.connect("editing_started", self.on_cell_edit_started, slno)
        
        if compact:
            self.cells['Description'].props.wrap_width = 300
        else:
            self.cells['Description'].props.wrap_width = 400
        self.cells['Description'].props.wrap_mode = 2
        self.cells['Rate'].props.xalign = 1
        self.cells['Tax'].props.xalign = 1
        self.cells['Discount'].props.xalign = 1
        
        # Intialise clipboard
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        
        self.update_store()

    def update_store(self):
        # Clear store
        self.store.clear()
        # Fill in data in treeview
        res_table = self.database.get_resource_table()
        for category, items in res_table.items():
            category_row = ['',category,'','','','','']
            
            if self.read_only:
                bools = [False]*7
            else:
                bools = [False,True] + [False]*5
            
            category_iter = self.store.append(None, category_row+bools)
            
            if self.read_only:
                bools = [False]*7
            else:
                bools = [True]*7
            
            for code, item in items.items():
                # Add items to store
                row = []
                for value in item:
                    if value is None:
                        row.append('')
                    else:    
                        row.append(str(value))
                item_iter = self.store.append(category_iter, row+bools)
                        
        # Expand all expanders
        self.tree.expand_all()
        
    def get_next_path(self, iter_path, reverse=False):
        if iter_path is None:
            return None
            
        iter_row = self.store.get_iter(iter_path)
        
        if not reverse:
            if self.store.iter_has_child(iter_row):
                return self.store.get_path(self.store.iter_nth_child(iter_row,0))
            elif self.store.iter_next(iter_row):
                return self.store.get_path(self.store.iter_next(iter_row))
            else:
                parent = self.store.iter_parent(iter_row)
                if parent:
                    if self.store.iter_next(parent):
                        if self.store.iter_next(parent):
                            return self.store.get_path(self.store.iter_next(parent))
                        else:
                            great_parent = self.store.iter_parent(parent)
                            if self.store.iter_next(great_parent):
                                return self.store.get_path(self.store.iter_next(great_parent))
        else:
            if self.store.iter_previous(iter_row):
                prev_row = self.store.iter_previous(iter_row)
                if self.store.iter_has_child(prev_row):
                    n_last_child = self.store.iter_n_children(prev_row) - 1
                    child = self.store.iter_nth_child(prev_row, n_last_child)
                    if self.store.iter_has_child(child):
                        n_last_grand_child = self.store.iter_n_children(child) - 1
                        grand_child = self.store.iter_nth_child(child, n_last_grand_child)
                        return self.store.get_path(grand_child)
                    else:
                        return self.store.get_path(child)
                else:
                    return self.store.get_path(self.store.iter_previous(iter_row))
            elif self.store.iter_parent(iter_row):
                return self.store.get_path(self.store.iter_parent(iter_row))
                
        return None
        
    def get_selected_paths(self):
        path_indices = []
        selection = self.tree.get_selection()
        if selection.count_selected_rows() != 0:  # if selection exists
            [tree, paths] = selection.get_selected_rows()
            for path in paths:
                path_index = path.get_indices()
                path_indices.append(path_index)
        return path_indices
        
    def get_selected(self, include_category=True):
        codes = OrderedDict()
        
        selection = self.tree.get_selection()
        if selection.count_selected_rows() != 0:  # if selection exists
            [tree, paths] = selection.get_selected_rows()
            for path in paths:
                path_index = tuple(path.get_indices())
                if len(path) == 1:
                    if include_category:
                        category = self.filter[path][1]
                        codes[path_index] = category
                elif len(path) == 2:
                    code = self.filter[path][0]
                    codes[path_index] = code

        return codes
        
    def set_selection(self, code):

        def search_func(model, path, iterator, data):
            code = data[0]
            if model[iterator][0] == code:
                data[1] = path
                return True
                
        data = [code, None]
        self.store.foreach(search_func, data)
        if data[1] is not None:
            self.tree.set_cursor(data[1])
            self.tree.scroll_to_cell(data[1], None)
            
    @undoable
    def add_category_at_selection(self, newcat):
        """Add category at selection"""
        
        paths = self.get_selected_paths()
        if paths:
            path = paths[-1]
        else:
            path = None
        self.database.insert_resource_category(newcat, path=path)
        self.update_store()
        
        yield "Add resource category item at path:'{}'".format(str(path))
        # Delete added resources
        self.database.delete_resource_category(newcat)
        self.update_store()
    
    @undoable
    def add_resource_at_selection(self, ress=None):
        """Add items at selection"""
        
        undocodes = []
        paths = self.get_selected_paths()
        
        # Setup position to insert
        if paths:
            path = paths[-1]
        else:
            path = None
            
        if ress:
            # Add multiple resource
            for slno, res in enumerate(ress):
                code = self.database.get_new_resource_code(shift=slno)
                undocodes.append(code)
                res.code = code

            self.database.insert_resource_multiple(ress, path=path)
            self.update_store()
            self.set_selection(code=res.code)
        else:
            # Setup blank resource and insert into database
            code = self.database.get_new_resource_code()

            res = data.schedule.ResourceItemModel(code = code,
                                                  description = '',
                                                  unit = '',
                                                  rate = 0,
                                                  category = None)
      
            if self.database.insert_resource(res, path=path):
                undocodes.append(code)
                self.update_store()
                self.set_selection(code=code)
        
        yield "Add resource data item at path:'{}'".format(str(path))
        # Delete added resources
        for code in undocodes:
            self.database.delete_resource(code)
        self.update_store()
        
    def delete_selected_item(self):
        selected = self.get_selected()
        affected_items = self.database.get_resource_dependency(selected)
        
        if affected_items:
            dialog = Gtk.MessageDialog(self.parent, 0, Gtk.MessageType.QUESTION,
                Gtk.ButtonsType.OK_CANCEL , "Are you sure you want to delete ?")
            dialog.format_secondary_text(
                "Analysis of items will be affected by this action and cannot be undone.")
            ret_code = dialog.run()
            dialog.destroy()
            
            if ret_code != Gtk.ResponseType.OK:
                return

        for path, code in selected.items():
            # Category
            if len(path) == 1:
                self.database.delete_resource_category(code)
            # Resource Items
            elif len(path) == 2:
                self.database.delete_resource(code)
        self.update_store()
                            
    def copy_selection(self):
        """Copy selected row to clipboard"""
        selected = self.get_selected()
        
        if selected: # if selection exists
            test_string = "ResourceView"
            
            items = []
            for path in selected:
                if len(path) == 2:
                    code = selected[path]
                    item = self.database.get_resource(code)
                    if item:
                        items.append(item)
            if items:
                text = codecs.encode(pickle.dumps([test_string, items]), "base64").decode() # dump item as text
                self.clipboard.set_text(text,-1) # push to clipboard
                log.info('ResourceView - copy_selection - Item copied to clipboard - ' + str(path))
                return
        # if no selection
        log.warning("ResourceView - copy_selection - No items selected to copy")
    
    def paste_at_selection(self):
        """Paste copied item at selected row"""
        text = self.clipboard.wait_for_text() # get text from clipboard
        if text != None:
            test_string = "ResourceView"
            try:
                itemlist = pickle.loads(codecs.decode(text.encode(), "base64"))  # recover item from string
                if itemlist[0] == test_string:
                    items = itemlist[1]
                    self.add_resource_at_selection(items)
            except:
                log.warning('ResourceView - paste_at_selection - No valid data in clipboard')
        else:
            log.warning('ResourceView - paste_at_selection - No text in clipboard')
            
                        
    @undoable
    def cell_renderer_text(self, path, column, oldvalue, newvalue):
        """Undoable function for modifying value of a treeview cell"""
        iterator = self.store.get_iter(Gtk.TreePath.new_from_indices(path))
        
        # Update category
        if len(path) == 1 and column == 1:
            
            if not self.database.update_resource_category(oldvalue, newvalue):
                log.warning('ScheduleView - cell_renderer_text - category not updated - ' + str(oldvalue) + ':' + str(newvalue))
            else:
                self.store[iterator][column] = newvalue
        
        # Update items     
        elif len(path) in [2,3]:
            code = self.store[iterator][0]
            if not self.database.update_resource(code, newvalue, column):
                log.warning('ScheduleView - cell_renderer_text - value not updated - ' + str(oldvalue) + ':' + str(newvalue) + ' {' + str(column) + '}')
            else:
                self.store[iterator][column] = newvalue

        yield "Change resource item at row:'{}' and column:'{}'".format(str(path), column)
        # Undo action
        if len(path) == 1:
            self.store[iterator][column] = oldvalue
            self.database.update_resource_category(newvalue, oldvalue)
        elif len(path) == 2:
            self.store[iterator][column] = oldvalue
            new_code = code
            if column == 0:
                new_code = newvalue
            self.database.update_resource(new_code, oldvalue, column)
    
        
    # Search functions
    
    def equal_func(self, model, column, key, iterator, cols):
        """Equal function for interactive search"""
        search_string = ''
        for col in cols:
            search_string += ' ' + model[iterator][col].lower()
        for word in key.split():
            if word.lower() not in search_string:
                return True
        return False

    def filter_func(self, model, model_iter, cols):
        """Searches in treestore"""
        
        def check_key(key, model_iter):
            if key is None or key == "":
                return True
            else:
                search_string = ''
                for col in cols:
                    if model[model_iter][col] is not None:
                        search_string += ' ' + model[model_iter][col].lower()
                for word in key.split():
                    if word.lower() not in search_string:
                        return False
                return True
        
        def search_children(key, model_iter):
            cur_iter = model.iter_children(model_iter)
            while cur_iter:
                if check_key(key, cur_iter) == True:
                    return True
                else:
                    code = search_children(key, cur_iter)
                    if code == True:
                        return True
                cur_iter = model.iter_next(cur_iter)
            return False

        key = self.search_field.get_text()
        # Check item
        if check_key(key, model_iter) == True:
            return True
        # Check children
        else:
            return search_children(key, model_iter)

    # Callbacks

    def on_search(self, entry):
        # Refilter model
        self.filter.refilter()
        # Expand all expanders
        self.tree.expand_all()
        
    def on_click_event(self, button, event):
        """Select item on double click"""
        # Grab focus
        self.tree.grab_focus()
        # Handle double clicks
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self.select_action()

    def on_key_press_treeview(self, treeview, event):
        """Handle keypress event"""
        keyname = event.get_keyval()[1]
        state = event.get_state()
        shift_pressed = bool(state & Gdk.ModifierType.SHIFT_MASK)
        control_pressed = bool(state & Gdk.ModifierType.CONTROL_MASK)
        
        if keyname in [Gdk.KEY_Escape]:  # Unselect all
            self.tree.get_selection().unselect_all()
            return
        elif keyname in [Gdk.KEY_Return, Gdk.KEY_KP_Enter]:  # Select element
            if control_pressed:
                self.select_action_alt()
            else:
                self.select_action()
        elif keyname == Gdk.KEY_f and control_pressed:  # Search keycode
            self.search_bar.set_search_mode(True)
        
        path, col = treeview.get_cursor()
        if path != None:
            columns = [c for c in treeview.get_columns()]
            colnum = columns.index(col)
            store = treeview.get_model()
            
            row_path = path.copy()
            
            if col in columns:
                if keyname in [Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab]:
                    if shift_pressed == 1:
                        # Search over editable states
                        while row_path:
                            # Determine starting column
                            # For same row
                            if row_path == path:
                                end = (colnum-1)+7
                            # For different row
                            else:
                                end = 13
                            for col in range(end,6,-1):
                                if self.store[row_path][col] == True:
                                    prev_column = columns[col-7]
                                    GLib.timeout_add(50, treeview.set_cursor, row_path, prev_column, True)
                                    return
                            row_path = self.get_next_path(row_path, reverse=True)
                    else:
                        # Search over editable states
                        while row_path:
                            # Determine starting column
                            # For same row
                            if row_path == path:
                                start = (colnum+1)+7
                            # For different row
                            else:
                                start = 7
                            for col in range(start, 14):
                                if self.store[row_path][col] == True:
                                    next_column = columns[col-7]
                                    GLib.timeout_add(50, treeview.set_cursor, row_path, next_column, True)
                                    return
                            row_path = self.get_next_path(row_path, reverse=False)
                            
    def select_action(self):
        pass
        
    def select_action_alt(self):
        pass
        
    def on_cell_edited_text(self, widget, path_str, new_text, column):
        """Treeview cell renderer for editable text field
        
            User Data:
                column: column in ListStore being edited
        """
        path = [int(part) for part in path_str.split(':')]
        iterator = self.store.get_iter_from_string(path_str)
        oldvalue = self.store[iterator][column]
        
        # Call undoable function only if there is a change in value
        if new_text != oldvalue:
            self.cell_renderer_text(path, column, oldvalue, new_text)

    def on_cell_edited_num(self, widget, path_str, new_text, column):
        """Treeview cell renderer for editable number field
        
            User Data:
                column: column in ListStore being edited
        """
        path = [int(part) for part in path_str.split(':')]
        iterator = self.store.get_iter_from_string(path_str)
        oldvalue = self.store[iterator][column]
        
        try:  # check whether item evaluates fine
            evaluated_no = eval(new_text)
            if evaluated_no == 0:
                evaluated = ''
            else:
                evaluated = str(evaluated_no)
        except:
            log.warning("ScheduleView - on_cell_edited_num - evaluation of [" 
            + new_text + "] failed")
            return
        
        # Call undoable function only if there is a change in value
        if evaluated != oldvalue:
            self.cell_renderer_text(path, column, oldvalue, evaluated)
            
    def on_cell_edit_started(self, widget, editable, path, column):
        """Fill in text from schedule when schedule view column get edited
        
            User Data:
                column: column in ListStore being edited
        """
        # Blockout uneditable columns
        editable.props.width_chars = 1
        

class SelectResourceDialog:
    """Shows a dialog to select a resource item """
        
    def __init__(self, parent, database, select_database_mode=False):
        """Setup dialog window and connect signals
        
            Arguments:
                parent: Parent window
                database: database of items to be displayed
                selected: Current selected item
        """
        log.info('SelectResourceDialog - Initialise')
        
        # Passed data
        self.database = database
        self.select_database_mode = select_database_mode

        # Setup dialog
        if select_database_mode:
            title = 'Select the database to load rates'
            self.dialog_window = Gtk.Dialog(title, parent, Gtk.DialogFlags.MODAL,
                (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                 'Load', Gtk.ResponseType.OK))
        else:
            title = 'Select the resource to be added'
            self.dialog_window = Gtk.Dialog(title, parent, Gtk.DialogFlags.MODAL,
                (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                 Gtk.STOCK_OK, Gtk.ResponseType.OK))
                 
        self.dialog_window.set_transient_for(parent)
        self.dialog_window.set_default_response(Gtk.ResponseType.OK)
        self.dialog_window.set_resizable(True)
        self.dialog_window.set_size_request(900,500)
        
        dialogBox = self.dialog_window.get_content_area()
        dialogBox.set_border_width(6)
        self.action_area = self.dialog_window.get_action_area()
        self.action_area.set_border_width(6)
        
        # Combobox for libraries
        self.library_combo = Gtk.ComboBoxText()
        
        if not select_database_mode:
            self.library_combo.append_text('Current')
            
        self.libraries = self.database.get_library_names()
        for library in self.libraries:
            if library:
                self.library_combo.append_text(str(library))
        self.library_combo.set_active(0)
                
        # Pack widgets
        box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 12)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        dialogBox.pack_start(box, True, True, 0)
        box.pack_start(self.library_combo, False, False, 0)
        box.pack_start(self.stack, True, True, 0)
        
        self.resourceviews = dict()
        
        if not select_database_mode:
            # Setup default database
            box_res = Gtk.Box.new(Gtk.Orientation.VERTICAL,0)
            self.stack.add_named(box_res, 'Current')
            res_view = ResourceView(self.dialog_window, 
                                            self.database, 
                                            box_res, 
                                            compact=True,
                                            read_only=True)
            # Overide functions of default resource view
            res_view.select_action = self.select_action
            self.resourceviews['Current'] = res_view
            
        for library in self.libraries:
            box_res = Gtk.Box.new(Gtk.Orientation.VERTICAL,0)
            self.stack.add_named(box_res, library)
            with self.database.using_library(library):
                res_view = ResourceView(self.dialog_window, 
                                        self.database, 
                                        box_res, 
                                        compact=True,
                                        read_only=True)
                self.resourceviews[library] = res_view
                # Overide functions of resource view
                res_view.select_action = self.select_action
            # Disable selection in database selection mode
            if select_database_mode:
                res_view.tree.get_selection().set_mode(Gtk.SelectionMode.NONE)
                
        if not select_database_mode:
            self.resourceview = self.resourceviews['Current']
        else:
            self.resourceview = self.resourceviews[self.libraries[0]]
            
        self.resourceview.tree.grab_focus()
        
        # Connect signals
        self.library_combo.connect("changed", self.on_combo_changed)
        
    def on_combo_changed(self, combo):
        name = combo.get_active_text()
        self.resourceview = self.resourceviews[name]
        self.stack.set_visible_child_name(name)
        self.resourceview.tree.grab_focus()

    def run(self):
        """Show dialog and return with resource
        
            Returns:
            Returns Resource or None if user does not select any item.
        """
        if not self.select_database_mode:
            # Update current item resource view
            self.resourceviews['Current'].update_store()
            
        # Show Dialog window
        self.dialog_window.show_all()
        response = self.dialog_window.run()
        
        # Evaluate response
        if response == Gtk.ResponseType.OK:
            if not self.select_database_mode:
                selected = self.resourceview.get_selected(include_category=False)
                if selected:
                    selected_code = list(selected.items())[-1][1]
                    # Get current name
                    index = self.library_combo.get_active()
                    if index == 0:
                        selected_resource = self.database.get_resource(selected_code)
                    else:
                        name = self.library_combo.get_active_text()
                        # Get resource from selected library
                        with self.database.using_library(name):
                            selected_resource = self.database.get_resource(selected_code)
                            
                    if selected_resource:
                        log.info('SelectResourceDialog - run - Selected - ' + selected_code)
                        self.dialog_window.hide()
                        return selected_resource
            else:
                index = self.library_combo.get_active()
                self.dialog_window.hide()
                return self.libraries[index]
                
        self.dialog_window.hide()
        log.info('SelectResourceDialog - run - Cancelled')
        return None
        
    def select_action(self):
        self.dialog_window.response(Gtk.ResponseType.OK)


class ResourceEntryDialog():
    """Creates a dialog box for entry of custom data fields
    
        Arguments:
            parent: Parent Window
            database: Schedule database
            item: Resource item for editing
    """
    
    def __init__(self, parent, database, custom_items, item=None):
        self.toplevel = parent
        self.database = database
        self.custom_items = custom_items
        
        self.entrys = {}
        captions = ['Code', 'Description', 'Unit', 'Rate', 'Tax', 'Discount', 'Reference']
        
        if item:
            caption = 'Edit Resource'
        else:
            caption = 'Add New Resource'

        self.dialog_window = Gtk.Dialog(caption, parent, Gtk.DialogFlags.MODAL,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             Gtk.STOCK_OK, Gtk.ResponseType.OK))
        self.dialog_window.set_border_width(6)
        self.dialog_window.set_size_request(600,-1)
        self.dialog_window.set_default_response(Gtk.ResponseType.OK)

        # Pack Dialog
        dialog_box = self.dialog_window.get_content_area()
        grid = Gtk.Grid()
        grid.set_column_spacing(6)
        grid.set_row_spacing(6)
        grid.set_border_width(6)
        grid.set_hexpand(True)
        dialog_box.add(grid)
        
        # Add text boxes
        for caption in captions:
            # Captions
            user_label = Gtk.Label(caption)
            user_label.set_halign(Gtk.Align.END)
            # Text Entry
            user_entry = Gtk.Entry()
            user_entry.set_hexpand(True)
            user_entry.set_activates_default(True)
            # Pack Widgets
            grid.attach_next_to(user_label, None, Gtk.PositionType.BOTTOM, 1, 1)
            grid.attach_next_to(user_entry, user_label, Gtk.PositionType.RIGHT, 1, 1)
            self.entrys[caption] = user_entry
        # Add combobox for categories
        # Combo box
        self.category_combo = Gtk.ComboBoxText.new_with_entry()
        self.category_combo_entry = self.category_combo.get_child()
        categories = self.database.get_resource_categories()
        for category in categories:
            if category:
                self.category_combo.append_text(str(category))
        # Caption
        category_label = Gtk.Label('Category')
        category_label.set_halign(Gtk.Align.END)
        # Pack Widgets
        grid.attach_next_to(category_label, None, Gtk.PositionType.BOTTOM, 1, 1)
        grid.attach_next_to(self.category_combo, category_label, Gtk.PositionType.RIGHT, 1, 1)
        
        # Add data
        if item:
            self.entrys['Code'].set_text(item.code)
            self.entrys['Description'].set_text(item.description)
            self.entrys['Unit'].set_text(item.unit)
            self.entrys['Rate'].set_text(item.rate)
            self.entrys['Tax'].set_text(item.vat)
            self.entrys['Discount'].set_text(item.discount)
            self.entrys['Reference'].set_text(item.reference)
            self.category_combo_entry.set_text(item.category)
        else:
            code_def = self.database.get_new_resource_code(exclude=self.custom_items)
            self.entrys['Code'].set_text(code_def)
            self.entrys['Description'].set_text('')
            self.entrys['Unit'].set_text('')
            self.entrys['Rate'].set_text('0')
            self.entrys['Tax'].set_text('0')
            self.entrys['Discount'].set_text('0')
            self.entrys['Reference'].set_text('')
            self.category_combo_entry.set_text('UNCATEGORISED')
            
                
    def run(self):
        """Display dialog box and modify Item Values in place
        
            Save modified values to "item_values" (item passed by reference)
            if responce is Ok. Discard modified values if response is Cancel.
            
            Returns:
                True on Ok
                False on Cancel
        """
        # Run dialog
        self.dialog_window.show_all()
        response = self.dialog_window.run()
        
        if response == Gtk.ResponseType.OK:
            # Get formated text and update item_values
            try:
                rate = Decimal(eval(self.entrys['Rate'].get_text()))
            except:
                self.entrys['Rate'].set_text('0')
                return self.run()
            try:
                tax = Decimal(eval(self.entrys['Tax'].get_text()))
            except:
                self.entrys['Tax'].set_text('0')
                return self.run()
            try:
                discount = Decimal(eval(self.entrys['Discount'].get_text()))
            except:
                self.entrys['Discount'].set_text('0')
                return self.run()
                
            category = self.category_combo.get_active_text()
            resource = data.schedule.ResourceItemModel(code = self.entrys['Code'].get_text(),
                                            description = self.entrys['Description'].get_text(),
                                            unit = self.entrys['Unit'].get_text(),
                                            rate = rate,
                                            vat = tax,
                                            discount = discount,
                                            reference = self.entrys['Reference'].get_text(),
                                            category = category)
            
            if self.database.check_insert_resource(resource):
                self.dialog_window.destroy()
                return [True,resource]
            else:
                # Show error message
                message = 'Error inserting item'
                dialogError = Gtk.MessageDialog(self.dialog_window,
                                     Gtk.DialogFlags.MODAL,
                                     Gtk.MessageType.ERROR,
                                     Gtk.ButtonsType.CLOSE,
                                     message)
                dialogError.run()
                dialogError.destroy()
                return self.run()
        else:
            self.dialog_window.destroy()
            return False
            
            
class ResourceUsageDialog():
    """Creates a dialog box for displaying resource usage
    
        Arguments:
            parent: Parent Window
            database: Schedule database
    """
    
    def __init__(self, parent, database):
        self.toplevel = parent
        self.database = database
        self.entrys = {}
        captions = ['Code', 'Description', 'Unit', 'Rate', 'Qty', 'Amount']
        expands = [False, True, False, False, False, False]
        widths = [100, 350, 100, 100, 100, 100]
        window_caption = 'Resource Usage'
        
        # Setup dialog
        self.dialog_window = Gtk.Dialog(window_caption, parent, Gtk.DialogFlags.MODAL,
            (Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        self.dialog_window.set_size_request(900,500)
        self.dialog_window.set_default_response(Gtk.ResponseType.CLOSE)
        self.action_area = self.dialog_window.get_action_area()
        self.action_area.set_border_width(6)
        
        # Setup treestore
        self.store = Gtk.TreeStore(*[str]*6)
        
        # Setup widgets
        self.box = self.dialog_window.get_content_area()
        self.scrolled = Gtk.ScrolledWindow()
        self.tree = Gtk.TreeView(self.store)
        
        # Pack widgets
        self.box.pack_start(self.scrolled, True, True, 0)
        self.scrolled.add(self.tree)
        
        # Setup tree view
        self.tree.set_grid_lines(3)
        self.tree.set_search_equal_func(self.equal_func, [0,1,2])
        self.columns = dict()
        self.cells = dict()
        for slno, [caption, expand, width] in enumerate(zip(captions, expands, widths)):
            column = Gtk.TreeViewColumn(caption)
            cell = Gtk.CellRendererText()
            self.tree.append_column(column)
            self.columns[caption] = column
            self.cells[caption] = cell
            column.pack_start(cell, expand)
            column.add_attribute(cell, "text", slno)
            column.set_fixed_width(width)
            column.set_resizable(True)
        self.cells['Description'].props.wrap_width = 300
        self.cells['Description'].props.wrap_mode = 2
        self.cells['Qty'].props.xalign = 1
        self.cells['Rate'].props.xalign = 1
        self.cells['Amount'].props.xalign = 0.8
        self.update_store()

    def update_store(self):
        # Clear store
        self.store.clear()
        # Fill in data in treeview
        res_table = self.database.get_res_usage()
        for code, item in sorted(res_table.items()):
            description = item[1]
            unit = item[2]
            qty = item[3]
            basicrate = Decimal(item[4])
            vat = Decimal(item[5]) if item[5] is not None else Decimal(0)
            discount = Decimal(item[6]) if item[6] is not None else Decimal(0)
            rate = basicrate*(1+vat/100)*(1-discount/100)
            amount = Currency(rate*qty)
            
            items_str = [code, description, unit, 
                         str(rate), str(qty), str(amount)]
            category_iter = self.store.append(None, items_str)
            
    def equal_func(self, model, column, key, iterator, cols):
        """Equal function for interactive search"""
        search_string = ''
        for col in cols:
            search_string += ' ' + model[iterator][col].lower()
        for word in key.split():
            if word.lower() not in search_string:
                return True
        return False
            
    def run(self):
        """Display dialog box"""
        # Run dialog
        self.dialog_window.show_all()
        self.dialog_window.run()
        self.dialog_window.destroy()
            
