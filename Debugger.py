#----------------------------------------------------------------------------
# Name:         Debugger.py
# Purpose:      wxPython debugger, currently a port of IDLE's debugger
#               written by Guido van Rossum
#
# Author:       Riaan Booysen 
#
# Created:      2000/01/11
# RCS-ID:       $Id$
# Copyright:    (c) Riaan Booysen
# Licence:      GPL
#----------------------------------------------------------------------------

# XXX I must still try to see if it's not possible the change code while
# XXX debugging, reload sometimes work
# XXX Going to source code on an error


from   wxPython.wx import *
import wxPython
import Editor, Preferences
import string, sys, os
from os import path
from repr import Repr
import bdb, traceback, linecache, imp
import Utils
from Preferences import pyPath
from PhonyApp import wxPhonyApp
    
wxID_STACKVIEW = NewId()
class StackViewCtrl(wxListCtrl):

    def __init__(self, parent, flist, browser):
        wxListCtrl.__init__(self, parent, wxID_STACKVIEW, style = wxLC_REPORT | wxLC_SINGLE_SEL )
        self.InsertColumn(0, 'Frame', wxLIST_FORMAT_LEFT, 150) 
        self.InsertColumn(1, 'Line', wxLIST_FORMAT_LEFT, 35)
        self.InsertColumn(2, 'Code', wxLIST_FORMAT_LEFT, 300)
        EVT_LIST_ITEM_SELECTED(self, wxID_STACKVIEW, self.OnStackItemSelected)
        EVT_LIST_ITEM_DESELECTED(self, wxID_STACKVIEW, self.OnStackItemDeselected)
        EVT_LEFT_DCLICK(self, self.OnGotoSource) 

        self.flist = flist
        self.browser = browser
        self.stack = []
        self.selection = -1

    def load_stack(self, stack, index=None):
        self.stack = stack
        self.DeleteAllItems()

        for i in range(len(stack)):
            frame, lineno = stack[i]
            try:
                modname = frame.f_globals['__name__']
            except:
                modname = "?"
            code = frame.f_code
            filename = code.co_filename
            funcname = code.co_name
            sourceline = linecache.getline(filename, lineno)
            sourceline = string.strip(sourceline)
            if funcname in ("?", "", None):
                item = "%s, line %d: %s" % (modname, lineno, sourceline)
                attrib = modname
            else:
                item = "%s.%s(), line %d: %s" % (modname, funcname,
                                                 lineno, sourceline)
                attrib = modname+'.'+funcname
                
            if i == index:
                item = "> " + item
            pos = self.GetItemCount()
            self.InsertStringItem(pos, attrib)
            self.SetStringItem(pos, 1, `lineno`, -1)
            self.SetStringItem(pos, 2, sourceline, -1)

    def OnStackItemSelected(self, event):
        self.selection = event.m_itemIndex

        if 0 <= self.selection < len(self.stack):
            self.browser.show_frame(self.stack[self.selection])
        
    def OnStackItemDeselected(self, event):
        self.selection = -1
            
    def OnGotoSource(self, event):
        if self.selection != -1:
            frame, lineno = self.stack[self.selection]
            try:
                modname = frame.f_globals['__name__']
            except:
                return
#                modname = "?"
            code = frame.f_code
            filename = code.co_filename
            
            if filename[0] != '<' and filename[-1] != '>':
                self.browser.model.editor.SetFocus()
                self.browser.model.editor.openOrGotoModule(filename)
                model = self.browser.model.editor.getActiveModulePage().model
                model.views['Source'].focus()
                model.views['Source'].SetFocus()
                model.views['Source'].selectLine(lineno - 1)

def get_stack(t=None, f=None):
    if t is None:
        t = sys.last_traceback
    stack = []
    if t and t.tb_frame is f:
        t = t.tb_next
    while f is not None:
        stack.append((f, f.f_lineno))
        if f is self.botframe:
            break
        f = f.f_back
    stack.reverse()
    while t is not None:
        stack.append((t.tb_frame, t.tb_lineno))
        t = t.tb_next
    return stack


def getexception(type=None, value=None):
    if type is None:
        type = sys.last_type
        value = sys.last_value
    if hasattr(type, "__name__"):
        type = type.__name__
    s = str(type)
    if value is not None:
        s = s + ": " + str(value)
    return s

[wxID_BREAKVIEW, wxID_BREAKSOURCE, wxID_BREAKEDIT, wxID_BREAKDELETE, wxID_BREAKENABLED,
 wxID_BREAKREFRESH] = map(lambda x: NewId(), range(6))

class BreakViewCtrl(wxListCtrl):
    brkImgLst = wxImageList(16, 16)
    brkImgLst.Add(wxBitmap('Images/Debug/Breakpoint-red.bmp', wxBITMAP_TYPE_BMP))
    brkImgLst.Add(wxBitmap('Images/Debug/Breakpoint-yellow.bmp', wxBITMAP_TYPE_BMP))
    brkImgLst.Add(wxBitmap('Images/Debug/Breakpoint-gray.bmp', wxBITMAP_TYPE_BMP))
    brkImgLst.Add(wxBitmap('Images/Debug/Breakpoint-blue.bmp', wxBITMAP_TYPE_BMP))


    def __init__(self, parent, debugger):#, flist, browser):
        wxListCtrl.__init__(self, parent, wxID_BREAKVIEW, style = wxLC_REPORT | wxLC_SINGLE_SEL )
        self.InsertColumn(0, 'Module', wxLIST_FORMAT_LEFT, 90) 
        self.InsertColumn(1, 'Line', wxLIST_FORMAT_CENTER, 40)
        self.InsertColumn(2, 'Ignore', wxLIST_FORMAT_CENTER, 45)
        self.InsertColumn(3, 'Hits', wxLIST_FORMAT_CENTER, 45)
        self.InsertColumn(4, 'Condition', wxLIST_FORMAT_LEFT, 250)
        EVT_LIST_ITEM_SELECTED(self, wxID_BREAKVIEW, self.OnBreakpointSelected)
        EVT_LIST_ITEM_DESELECTED(self, wxID_BREAKVIEW, self.OnBreakpointDeselected)
        EVT_LEFT_DCLICK(self, self.OnGotoSource) 

        EVT_RIGHT_DOWN(self, self.OnRightDown)
        EVT_COMMAND_RIGHT_CLICK(self, -1, self.OnRightClick)
        EVT_RIGHT_UP(self, self.OnRightClick)
        
        self.menu = wxMenu()

        self.menu.Append(wxID_BREAKSOURCE, 'Goto source')
        self.menu.Append(wxID_BREAKREFRESH, 'Refresh')
        self.menu.Append(-1, '-')
        self.menu.Append(wxID_BREAKEDIT, 'Edit')
        self.menu.Append(wxID_BREAKDELETE, 'Delete')
        self.menu.Append(-1, '-')
        self.menu.Append(wxID_BREAKENABLED, 'Enabled', checkable = true)
        self.menu.Check(wxID_BREAKENABLED, true)
        EVT_MENU(self, wxID_BREAKSOURCE, self.OnGotoSource)
        EVT_MENU(self, wxID_BREAKREFRESH, self.OnRefresh)
        EVT_MENU(self, wxID_BREAKEDIT, self.OnEdit)
        EVT_MENU(self, wxID_BREAKDELETE, self.OnDelete)
        EVT_MENU(self, wxID_BREAKENABLED, self.OnToggleEnabled)
        self.x = self.y = 0

        self.SetImageList(self.brkImgLst, wxIMAGE_LIST_SMALL)

        self.selection = -1
        self.debugger = debugger
    
    def bpList(self):
        bpl = []
        for bp in bdb.Breakpoint.bpbynumber:
            if bp: bpl.append(bp)
        return bpl
     
    def refreshList(self):
        self.selection = -1
        self.DeleteAllItems()
        for bp in self.bpList():
            p = self.GetItemCount()
            imgIdx = 0
            if not bp.enabled:
                imgIdx = 2
            elif bp.temporary: imgIdx = 3

            self.InsertImageStringItem(p, path.basename(bp.file), imgIdx)
            self.SetStringItem(p, 1, `bp.line`)
            if bp.enabled: self.SetStringItem(p, 3, '*')
            self.SetStringItem(p, 2, `bp.ignore`)
            self.SetStringItem(p, 3, `bp.hits`)
            try: self.SetStringItem(p, 4, bp.condition)
            except: pass
    
    def addBreakpoint(self, filename, lineno):
        self.refreshList()

    def OnBreakpointSelected(self, event):
        self.selection = event.m_itemIndex
        
    def OnBreakpointDeselected(self, event):
        self.selection = -1
    
    def OnGotoSource(self, event):
        if self.selection != -1:
            bp = self.bpList()[self.selection]
            self.debugger.model.editor.SetFocus()
            self.debugger.model.editor.openOrGotoModule(bp.file)
            model = self.debugger.model.editor.getActiveModulePage().model
            model.views['Source'].focus()
            model.views['Source'].SetFocus()
            model.views['Source'].selectLine(bp.line - 1)

    def OnEdit(self, event):
        pass

    def OnDelete(self, event):
        if self.selection != -1:
            bp = self.bpList()[self.selection]
            self.debugger.clear_break(bp.file, bp.line)
            
            self.refreshList()

    def OnRefresh(self, event):
        self.refreshList()

    def OnToggleEnabled(self, event):
        if self.selection != -1:
            bp = self.bpList()[self.selection]
            bp.enabled = not bp.enabled
            self.refreshList()
         
    def OnRightDown(self, event):
        self.x = event.GetX()
        self.y = event.GetY()

    def OnRightClick(self, event):
        if self.selection != -1:
            self.menu.Check(wxID_BREAKENABLED, self.bpList()[self.selection].enabled)
            self.PopupMenu(self.menu, wxPoint(self.x, self.y))
        

# XXX Expose classes' dicts as indented items
wxID_NSVIEW = NewId()
class NamespaceViewCtrl(wxListCtrl):
    def __init__(self, parent, add_watch, is_local, name, dict=None):
        wxListCtrl.__init__(self, parent, wxID_NSVIEW, style = wxLC_REPORT | wxLC_SINGLE_SEL )
        self.InsertColumn(0, 'Attribute', wxLIST_FORMAT_LEFT, 125) 
        self.InsertColumn(1, 'Value', wxLIST_FORMAT_LEFT, 200)

        EVT_LIST_ITEM_SELECTED(self, -1, self.OnItemSelect)
        EVT_LIST_ITEM_DESELECTED(self, -1, self.OnItemDeselect)
        self.selected = -1

        EVT_RIGHT_DOWN(self, self.OnRightDown)
        EVT_COMMAND_RIGHT_CLICK(self, -1, self.OnRightClick)
        EVT_RIGHT_UP(self, self.OnRightClick)
        
        self.is_local = is_local
            
        self.menu = wxMenu()

        idAs = NewId()
        idA = NewId()
        self.menu.Append(idAs, 'Add as watch')
        self.menu.Append(idA, 'Add a %s watch' % name)
        EVT_MENU(self, idAs, self.OnAddAsWatch)
        EVT_MENU(self, idA, self.OnAddAWatch)
        self.x = self.y = 0
 
        self.repr = Repr()
        self.repr.maxstring = 60
        self.repr.maxother = 60
        self.names = []
        
        self.add_watch = add_watch

        self.load_dict(dict)

    dict = -1

    def load_dict(self, dict, force=0):
        if dict is self.dict and not force:
            return

        self.DeleteAllItems()
        self.dict = None
                
        if not dict:
            pass
        else:
            self.names = dict.keys()
            self.names.sort()
            row = 0
            for name in self.names:
                value = dict[name]
                svalue = self.repr.repr(value) # repr(value)

                self.InsertStringItem(row, name)
                self.SetStringItem(row, 1, svalue, -1)
                
                row = row + 1

        self.dict = dict
    
    def OnAddAsWatch(self, event):
        if self.selected != -1:
            name = self.names[self.selected]
            self.add_watch(name, self.is_local)

    def OnAddAWatch(self, event):
        self.add_watch('', self.is_local)

    def OnItemSelect(self, event):
        self.selected = event.m_itemIndex

    def OnItemDeselect(self, event):
        self.selected = -1

    def OnRightDown(self, event):
        self.x = event.GetX()
        self.y = event.GetY()

    def OnRightClick(self, event):
        self.PopupMenu(self.menu, wxPoint(self.x, self.y))

##    def close(self):
##        self.frame.destroy()

wxID_WATCHVIEW = NewId()
class WatchViewCtrl(wxListCtrl):

    def __init__(self, parent, images):
        wxListCtrl.__init__(self, parent, wxID_WATCHVIEW, style = wxLC_REPORT | wxLC_SINGLE_SEL )
        self.InsertColumn(0, 'Attribute', wxLIST_FORMAT_LEFT, 125) 
        self.InsertColumn(1, 'Value', wxLIST_FORMAT_LEFT, 200)
 
        self.repr = Repr()
        self.repr.maxstring = 60
        self.repr.maxother = 60
        
        self.watches = []

        self.SetImageList(images, wxIMAGE_LIST_SMALL)

        EVT_LIST_ITEM_SELECTED(self, -1, self.OnItemSelect)
        EVT_LIST_ITEM_DESELECTED(self, -1, self.OnItemDeselect)
        self.selected = -1

        EVT_RIGHT_DOWN(self, self.OnRightDown)
        EVT_COMMAND_RIGHT_CLICK(self, -1, self.OnRightClick)
        EVT_RIGHT_UP(self, self.OnRightClick)

        self.menu = wxMenu()

        id = NewId()
        self.menu.Append(id, 'Delete')
        EVT_MENU(self, id, self.OnDelete)
        self.x = self.y = 0

    dict = -1
    
    def add_watch(self, name, local):
        if name: 
            self.watches.append((name, local))
        else:  
            dlg = wxTextEntryDialog(self, 'Enter name:', 'Add a watch:', '')
            try:
                if dlg.ShowModal() == wxID_OK:
                    self.watches.append((dlg.GetValue(), local))
            finally:
                dlg.Destroy()         

    def load_dict(self, localsDict, globalsDict, force=0):
##        if ict is self.dict and not force:
##            return

        self.DeleteAllItems()
        row = 0
        for name, local in self.watches:
            if local:
                try: 
                    value = self.repr.repr(localsDict[name])
                except:
                    try:
                        value = eval(name, globalsDict, localsDict)
                    except Exception, message:
                        value = '??? (%s)' % message
                idx = 3
            else:
                try: 
                    value = self.repr.repr(globalsDict[name])
                except:
                    try:
                        value = eval(name, globalsDict)
                    except Exception, message:
                        value = '??? (%s)' % message
                idx = 4

            svalue = self.repr.repr(value) # repr(value)

            self.InsertImageStringItem(row, name, idx)
            self.SetStringItem(row, 1, svalue, idx)
            
            row = row + 1

    def OnDelete(self, event):
        if self.selected != -1:
            del self.watches[self.selected]
            self.DeleteItem(self.selected)

    def OnItemSelect(self, event):
        self.selected = event.m_itemIndex

    def OnItemDeselect(self, event):
        self.selected = -1

    def OnRightDown(self, event):
        self.x = event.GetX()
        self.y = event.GetY()

    def OnRightClick(self, event):
        self.PopupMenu(self.menu, wxPoint(self.x, self.y))

class DebugStatusBar(wxStatusBar):
    def __init__(self, parent):
        wxStatusBar.__init__(self, parent, -1)
        self.SetFieldsCount(2)

        rect = self.GetFieldRect(0)
        self.status = wxStaticText(self, 1001, 'Ready')
        self.status.SetDimensions(rect.x+2, rect.y+2, rect.width-4, rect.height-4)

        rect = self.GetFieldRect(1)
        self.error = wxStaticText(self, 1002, ' ')
        self.error.SetBackgroundColour(wxNamedColour('white'))
        self.error.SetDimensions(rect.x+2, rect.y+2, rect.width-4, rect.height-4)


        dc = wxClientDC(self)
        dc.SetFont(self.GetFont())
        (w,h) = dc.GetTextExtent('X')
        h = int(h * 1.8)
        self.SetSize(wxSize(100, h))

    def writeError(self, message):
        if message:
            self.error.SetBackgroundColour(wxNamedColour('yellow'))
        else:
            self.error.SetBackgroundColour(wxNamedColour('white'))
        self.error.SetLabel(message)

        rect = self.GetFieldRect(1)
        self.error.SetDimensions(rect.x+2, rect.y+2, rect.width-4, rect.height-4)

    def OnSize(self, event):
        rect = self.GetFieldRect(0)
        self.status.SetDimensions(rect.x+2, rect.y+2, rect.width-4, rect.height-4)

        rect = self.GetFieldRect(1)
        self.error.SetDimensions(rect.x+2, rect.y+2, rect.width-4, rect.height-4)

class DebuggerFrame(wxFrame, bdb.Bdb):
    viewsImgLst = wxImageList(16, 16)
    viewsImgLst.Add(wxBitmap('Images/Debug/Stack.bmp', wxBITMAP_TYPE_BMP))
    viewsImgLst.Add(wxBitmap('Images/Debug/Breakpoints.bmp', wxBITMAP_TYPE_BMP))
    viewsImgLst.Add(wxBitmap('Images/Debug/Watches.bmp', wxBITMAP_TYPE_BMP))
    viewsImgLst.Add(wxBitmap('Images/Debug/Locals.bmp', wxBITMAP_TYPE_BMP))
    viewsImgLst.Add(wxBitmap('Images/Debug/Globals.bmp', wxBITMAP_TYPE_BMP))
    viewsImgLst.Add(wxBitmap('Images/Debug/Output.bmp', wxBITMAP_TYPE_BMP))

    def __init__(self, model, stack = None):
        bdb.Bdb.__init__(self)
        wxFrame.__init__(self, model.editor, -1, 'Debugger - %s - %s' \
          % (path.basename(model.filename), model.filename),
          wxPoint(0, Preferences.paletteHeight), 
          wxSize(Preferences.inspWidth, Preferences.bottomHeight))

        if wxPlatform == '__WXMSW__':
	    self.icon = wxIcon(Preferences.toPyPath('Images\\Icons\\Debug.ico'), wxBITMAP_TYPE_ICO)
	    self.SetIcon(self.icon)

        self.interacting = 0
        self.filename = model.filename
#        self.app = app
        self.model = model

        self.sb = DebugStatusBar(self)
        self.SetStatusBar(self.sb)

        self.toolbar = wxToolBar(self, -1)#wxTB_HORIZONTAL|wxNO_BORDER)
        self.SetToolBar(self.toolbar)
        
        Utils.AddToolButtonBmpFile(self, self.toolbar, path.join(pyPath, 'Images', 'Debug',
          'Debug.bmp'),  'Debug', self.OnDebug)
        Utils.AddToolButtonBmpFile(self, self.toolbar, path.join(pyPath, 'Images', 'Debug',
          'Step.bmp'),  'Step', self.OnStep)
        Utils.AddToolButtonBmpFile(self, self.toolbar, path.join(pyPath, 'Images', 'Debug',
          'Over.bmp'),  'Over', self.OnOver)
        Utils.AddToolButtonBmpFile(self, self.toolbar, path.join(pyPath, 'Images', 'Debug',
          'Out.bmp'),  'Out', self.OnOut)
        Utils.AddToolButtonBmpFile(self, self.toolbar, path.join(pyPath, 'Images', 'Debug',
          'Stop.bmp'),  'Stop', self.OnStop)
        self.toolbar.AddSeparator()
        Utils.AddToggleToolButtonBmpFile(self, self.toolbar, path.join(pyPath, 'Images', 'Debug',
          'SourceTrace-Off.bmp'),  path.join(pyPath, 'Images', 'Debug',
          'SourceTrace-Off.bmp'),'Source trace', self.OnSourceTrace)

        
        self.toolbar.Realize()
    
        self.splitter = wxSplitterWindow(self, -1, style = wxSP_NOBORDER)
 
    
        # Create a Notebook
        self.nbTop = wxNotebook(self.splitter, -1)
        if wxPlatform == '__WXMSW__':
            self.nbTop.SetImageList(self.viewsImgLst)
        
        self.stack = StackViewCtrl(self.nbTop, None, self)
        if stack is None:
            try:
                stack = get_stack()
                self.stack.load_stack(stack)
            except:
                pass
        else:
            self.stack.load_stack(stack)

        if wxPlatform == '__WXMSW__':
            self.nbTop.AddPage(self.stack, 'Stack', imageId = 0)
        elif wxPlatform == '__WXGTK__':
            self.nbTop.AddPage(self.stack, 'Stack')

        self.breakpts = BreakViewCtrl(self.nbTop, self)
        if wxPlatform == '__WXMSW__':
            self.nbTop.AddPage(self.breakpts, 'Breakpoints', imageId = 1)
        elif wxPlatform == '__WXGTK__':
            self.nbTop.AddPage(self.breakpts, 'Breakpoints')

        self.outp = wxTextCtrl(self.nbTop, -1, '', style = wxTE_MULTILINE)
        self.outp.SetFont(wxFont(7, wxDEFAULT, wxNORMAL, wxNORMAL, false))
        if wxPlatform == '__WXMSW__':
            self.nbTop.AddPage(self.outp, 'Output', imageId = 5)
        elif wxPlatform == '__WXGTK__':
            self.nbTop.AddPage(self.outp, 'Output')

        # Create a Notebook
        self.nbBottom = wxNotebook(self.splitter, -1)
        if wxPlatform == '__WXMSW__':
            self.nbBottom.SetImageList(self.viewsImgLst)
            
        self.watches = WatchViewCtrl(self.nbBottom, self.viewsImgLst)
        if wxPlatform == '__WXMSW__':
            self.nbBottom.AddPage(self.watches, 'Watches', imageId = 2)
        elif wxPlatform == '__WXGTK__':
            self.nbBottom.AddPage(self.watches, 'Watches')

        self.locs = NamespaceViewCtrl(self.nbBottom, self.add_watch, 1, 'local')
        if wxPlatform == '__WXMSW__':
            self.nbBottom.AddPage(self.locs, 'Locals', imageId = 3)
        elif wxPlatform == '__WXGTK__':
            self.nbBottom.AddPage(self.locs, 'Locals')

        self.globs = NamespaceViewCtrl(self.nbBottom, self.add_watch, 0, 'global')
        
        if wxPlatform == '__WXMSW__':
            self.nbBottom.AddPage(self.globs, 'Globals', imageId = 4)
        elif wxPlatform == '__WXGTK__':
            self.nbBottom.AddPage(self.globs, 'Globals')
        
        self.splitter.SetMinimumPaneSize(40)
        self.splitter.SplitHorizontally(self.nbTop, self.nbBottom)
        self.splitter.SetSashPosition(175)
        
        self.mlc = 0
        self.frame = None
    
    def add_watch(self, name, local):
        self.watches.add_watch(name, local)
        self.nbBottom.SetSelection(0)
        self.show_variables()        
        
    def show_variables(self, force=0):
        frame = self.frame
        if not frame:
            ldict = gdict = None
        else:
            ldict = frame.f_locals
            gdict = frame.f_globals
            if self.locs and self.globs and ldict is gdict:
                ldict = None
        if self.locs:
            self.locs.load_dict(ldict, force)
        if self.globs:
            self.globs.load_dict(gdict, force)
        
        self.watches.load_dict(ldict, gdict, force)

    def show_frame(self, (frame, lineno)):
        self.frame = frame
        self.show_variables()


    def startMainLoop(self):
        self.model.editor.app.MainLoop()
        self.mlc = self.mlc + 1
        
        print 'start', self.mlc
        
    def stopMainLoop(self):
        self.model.editor.app.ExitMainLoop()
        self.mlc = self.mlc - 1

        print 'stop', self.mlc
    
#---------------------------------------------------------------------------

    def canonic(self, filename):
        # Canonicalize filename -- called by Bdb
        return os.path.normcase(os.path.abspath(filename))

    def do_clear(self, arg):
        self.clear_bpbynumber(arg)

    def debug_file(self, filename):
        filename = path.join(pyPath, filename)
        saveout = sys.stdout
        saveerr = sys.stderr

        owin = self.outp
        tmpApp = wxPython.wx.wxApp
        wxPhonyApp.debugger = self
        wxPython.wx.wxApp = wxPhonyApp
        
        modpth = os.path.dirname(filename)
        sys.path.append(modpth)
        try:
            sys.stderr = Editor.PseudoFileErr(owin)
            try:
                sys.stdout = Editor.PseudoFileOut(owin)
                try:
                    modname, ext = os.path.splitext(os.path.basename(filename))
                    if sys.modules.has_key(modname):
                        mod = sys.modules[modname]
                    else:
                        mod = imp.new_module(modname)
                        sys.modules[modname] = mod
                        
                    mod.__file__ = filename

                    self.run("execfile(%s)" % `filename`, mod.__dict__)
                except:
                    (sys.last_type, sys.last_value,
                     sys.last_traceback) = sys.exc_info()
                    linecache.checkcache()
                    traceback.print_exc()
            finally:
                sys.stdout = saveout
        finally:
            sys.stderr = saveerr
            wxPython.wx.wxApp = tmpApp
            sys.path.remove(modpth)

    def run(self, *args):
#        print args
        try:
            self.sb.status.SetLabel('Running.')
            self.interacting = 1
            return apply(bdb.Bdb.run, (self,) + args)
        finally:
            self.interacting = 0
            self.sb.status.SetLabel('Finished.')

    def user_line(self, frame):
        self.interaction(frame)

    def user_return(self, frame, rv):
        # XXX show rv?
        ##self.interaction(frame)
        pass

    def user_exception(self, frame, info):
        self.interaction(frame, info)

    def interaction(self, frame, info=None):
        self.frame = frame
        code = frame.f_code
        file = code.co_filename
        base = os.path.basename(file)
        lineno = frame.f_lineno

        message = "%s:%s" % (base, lineno)
        if code.co_name != "?":
            message = "%s: %s()" % (message, code.co_name)

        self.sb.status.SetLabel(message)

        if info:
            type, value, tb = info
            try:
                m1 = type.__name__
            except AttributeError:
                m1 = "%s" % str(type)
            if value is not None:
                try:
                    m1 = "%s: %s" % (m1, str(value))
                except:
                    pass
            bg = wxNamedColour('yellow')
        else:
            m1 = ''
            tb = None
            bg = wxNamedColour('white')#self.errorbg

        self.sb.writeError(m1)
        
        sv = self.stack
        if sv:
            stack, i = self.get_stack(self.frame, tb)
            sv.load_stack(stack, i)

        if (string.lower(file), lineno) in bdb.Breakpoint.bplist.keys():
            self.sb.error.SetBackgroundColour(wxNamedColour('red'))
            self.sb.error.SetLabel('Breakpoint.')

            rect = self.sb.GetFieldRect(1)
            self.sb.error.SetDimensions(rect.x+2, rect.y+2, rect.width-4, rect.height-4)
            
        self.breakpts.refreshList()
        self.selectSourceLine()

        self.startMainLoop()

        self.sb.status.SetLabel('')
        self.sb.writeError('')

        self.frame = None

    def selectSourceLine(self):
        if self.stack.stack:
            stack = self.stack.stack
            print stack
            frame, lineno = stack[len(stack)-1]
            try:
                modname = frame.f_globals['__name__']
            except:
                return
            code = frame.f_code
            filename = code.co_filename
    #            funcname = code.co_name
            
            if filename[0] != '<' and filename[-1] != '>':
                self.model.editor.SetFocus()
                self.model.editor.openOrGotoModule(filename)
                model = self.model.editor.getActiveModulePage().model
                model.views['Source'].focus()
                model.views['Source'].SetFocus()
                model.views['Source'].selectLine(lineno - 1)
        

    def OnDebug(self, event):
        if self.interacting:
            self.set_continue()
            self.stopMainLoop()
        else:
            self.debug_file(self.filename)

    def OnStep(self, event):
        self.set_step()
        self.stopMainLoop()

    def OnOver(self, event):
        self.set_next(self.frame)
        self.stopMainLoop()

    def OnOut(self, event):
        self.set_return(self.frame)
        self.stopMainLoop()

    def OnStop(self, event):
        wxPhonyApp.inMainLoop = false
        self.set_quit()
        self.stopMainLoop()
    
    def set_breakpoint_here(self, filename, lineno, tmp):
        self.nbTop.SetSelection(1)
        filename = self.canonic(filename)
        msg = self.set_break(filename, lineno, tmp)
        self.breakpts.refreshList()

    # A literal copy of Bdb.set_break() without the print statement at the end
    def set_break(self, filename, lineno, temporary=0, cond = None):
        import linecache # Import as late as possible
        line = linecache.getline(filename, lineno)
        if not line:
                return 'That line does not exist!'
        if not self.breaks.has_key(filename):
                self.breaks[filename] = []
        list = self.breaks[filename]
        if not lineno in list:
                list.append(lineno)
        bp = bdb.Breakpoint(filename, lineno, temporary, cond)

    def OnSourceTrace(self, event):
        pass

    def OnCloseWindow(self, event):
        if self.interacting:
            # XXX mmm
            self.OnStop(self, None)
        self.Destroy()
        self.model.editor.debugger = None        
        event.Skip()
        



