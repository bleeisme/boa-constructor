#-----------------------------------------------------------------------------
# Name:        PySourceView.py
# Purpose:     Python Source code View
#
# Author:      Riaan Booysen
#
# Created:     2000/04/26
# RCS-ID:      $Id$
# Copyright:   (c) 1999 - 2001
# Licence:     GPL
#-----------------------------------------------------------------------------
import os, string, bdb, sys

#sys.path.insert(0, '..')

from wxPython.wx import *
from wxPython.stc import *

import ProfileView, Search, Help, Preferences, ShellEditor, Utils

from SourceViews import EditorStyledTextCtrl, indentLevel
from StyledTextCtrls import PythonStyledTextCtrlMix, BrowseStyledTextCtrlMix,\
     FoldingStyledTextCtrlMix, AutoCompleteCodeHelpSTCMix, CallTipCodeHelpSTCMix,\
     idWord, new_stc, old_stc, object_delim
from PrefsKeys import keyDefs
import methodparse
import wxNamespace

brkPtMrk = 1
stepPosMrk = 2
tmpBrkPtMrk = 3
markPlaceMrk = 4

class PythonSourceView(EditorStyledTextCtrl, PythonStyledTextCtrlMix,
                       BrowseStyledTextCtrlMix, FoldingStyledTextCtrlMix,
                       AutoCompleteCodeHelpSTCMix, CallTipCodeHelpSTCMix):
    viewName = 'Source'
    breakBmp = 'Images/Debug/Breakpoints.bmp'
    runCrsBmp = 'Images/Editor/RunToCursor.bmp'
    runAppBmp = 'Images/Debug/RunApp.bmp'
    runBmp = 'Images/Debug/Run.bmp'
    compileBmp = 'Images/Debug/Compile.bmp'
    debugBmp = 'Images/Debug/Debug.bmp'
    modInfoBmp = 'Images/Modules/InfoBlock.bmp'
    profileBmp = 'Images/Debug/Profile.bmp'
    def __init__(self, parent, model):
        if hasattr(model, 'app') and model.app:
            a2 = (('Run application', self.OnRunApp, self.runAppBmp, keyDefs['RunApp']),)
        else:
            a2 = ()
        a1 = (('-', None, '', ()),
              ('Comment', self.OnComment, '-', keyDefs['Comment']),
              ('Uncomment', self.OnUnComment, '-', keyDefs['Uncomment']),
              ('Indent', self.OnIndent, '-', keyDefs['Indent']),
              ('Dedent', self.OnDedent, '-', keyDefs['Dedent']),
              ('Reindent whole file', self.OnReindent, '-', ()),
              ('-', None, '-', ()),
              ('Profile', self.OnProfile, self.profileBmp, ()),
              ('Check source', self.OnCompile, self.compileBmp, keyDefs['CheckSource']))
        a3 = (('Run module', self.OnRun, self.runBmp, keyDefs['RunMod']),
              ('Run module with parameters', self.OnRunParams, '-', ()),
              ('Debug', self.OnDebug, self.debugBmp, keyDefs['Debug']),
              ('Debug with parameters', self.OnDebugParams, '-', ()),
              ('Step in', self.OnDebugStepIn, '-', keyDefs['DebugStep']),
              ('Step over', self.OnDebugStepOver, '-', keyDefs['DebugOver']),
              ('Step out', self.OnDebugStepOut, '-', keyDefs['DebugOut']),
              ('-', None, '', ()),
              ('Run to cursor', self.OnRunToCursor, self.runCrsBmp, ()),
              ('Toggle breakpoint', self.OnSetBreakPoint, self.breakBmp, keyDefs['ToggleBrk']),
              ('Load breakpoints', self.OnLoadBreakPoints, '-', ()),
              ('Save breakpoints', self.OnSaveBreakPoints, '-', ()),
              ('-', None, '', ()),
              ('+View whitespace', self.OnViewWhitespace, '-', ()),
              ('+View EOL characters', self.OnViewEOL, '-', ()),
              ('-', None, '-', ()),
              ('Add module info', self.OnAddModuleInfo, self.modInfoBmp, ()),
              ('Add comment line', self.OnAddCommentLine, '-', keyDefs['DashLine']),
              ('Add simple app', self.OnAddSimpleApp, '-', ()),
              ('Code transformation', self.OnAddClassAtCursor, '-', keyDefs['CodeXform']),
              ('Code completion', self.OnCompleteCode, '-', keyDefs['CodeComplete']),
              ('Call tips', self.OnParamTips, '-', keyDefs['CallTips']),
              ('-', None, '-', ()),
              ('Context help', self.OnContextHelp, '-', keyDefs['ContextHelp']))


        wxID_PYTHONSOURCEVIEW = wxNewId()

        EditorStyledTextCtrl.__init__(self, parent, wxID_PYTHONSOURCEVIEW,
          model, a1 + a2 + a3, -1)
        PythonStyledTextCtrlMix.__init__(self, wxID_PYTHONSOURCEVIEW, 0)
        BrowseStyledTextCtrlMix.__init__(self)
        FoldingStyledTextCtrlMix.__init__(self, wxID_PYTHONSOURCEVIEW, 2)
        CallTipCodeHelpSTCMix.__init__(self)

        # Initialise breakpts from file and bdb.Breakpoint
        self.tryLoadBreakpoints()
        filename = string.lower(self.model.filename)
        for file, lineno in bdb.Breakpoint.bplist.keys():
            if file == filename:
                for bp in bdb.Breakpoint.bplist[(file, lineno)]:
                    self.breaks[lineno] = bp

        self.lsp = 0
        # XXX These could be persisted
        self.lastRunParams = ''
        self.lastDebugParams = ''

        # last line # that was edited
        self.damagedLine = -1

        self.SetMarginType(1, wxSTC_MARGIN_SYMBOL)
        self.SetMarginWidth(1, 12)
        self.SetMarginSensitive(1, true)
        self.MarkerDefine(brkPtMrk, wxSTC_MARK_CIRCLE, 'BLACK', 'RED')
        self.MarkerDefine(stepPosMrk, wxSTC_MARK_SHORTARROW, 'NAVY', 'BLUE')
        self.MarkerDefine(tmpBrkPtMrk, wxSTC_MARK_CIRCLE, 'BLACK', 'BLUE')
        self.CallTipSetBackground(wxColour(255, 255, 232))
        if new_stc:
            self.AutoCompSetIgnoreCase(true)

        # Error indicator
        self.IndicatorSetStyle(1, wxSTC_INDIC_SQUIGGLE)
        self.IndicatorSetForeground(1, wxRED)

        self.SetBufferedDraw(true)

        # Don't use event, override method from Browser parent
##        EVT_KEY_DOWN(self, self.OnKeyPressed)

        EVT_STC_CHARADDED(self, wxID_PYTHONSOURCEVIEW, self.OnAddChar)

#        EVT_STC_MODIFIED(self, wxID_PYTHONSOURCEVIEW, self.OnModified)

##        EVT_STC_CMDKEY(self, wxID_PYTHONSOURCEVIEW, self.OnKeyPressed)
        self.active = true

    def refreshCtrl(self):
        EditorStyledTextCtrl.refreshCtrl(self)
        self.setInitialBreakpoints()

    def processComment(self, textLst):
        return map(lambda l: '##%s'%l, textLst)

    def processUncomment(self, textLst):
        for idx in range(len(textLst)):
            if len(textLst[idx]) >= 2 and textLst[idx][:2] == '##':
                textLst[idx] = textLst[idx][2:]
        return textLst

    def processIndent(self, textLst):
        return map(lambda l: '%s%s'%(indentLevel*' ', l), textLst)

    def processDedent(self, textLst):
        for idx in range(len(textLst)):
            if len(textLst[idx]) >= indentLevel and \
              textLst[idx][:indentLevel] == indentLevel*' ':
                textLst[idx] = textLst[idx][indentLevel:]
        return textLst

    def checkCallTipHighlight(self):
        if self.CallTipActive():
            pass

#---Call Tips-------------------------------------------------------------------

    def getTipValue(self, word, lnNo):
        """ Overwritten Mixin method, returns string to display as tool tip """
        module = self.model.getModule()
        objPth = string.split(word, '.')
        safesplit = methodparse.safesplitfields

        cls = module.getClassForLineNo(lnNo)
        if cls:
            if len(objPth) == 1:
                if module.classes.has_key(objPth[0]) and \
                     module.classes[objPth[0]].methods.has_key('__init__'):
                    return self.prepareModSigTip(objPth[0],
                        module.classes[objPth[0]].methods['__init__'].signature)
                elif module.functions.has_key(objPth[0]):
                    return self.prepareModSigTip(objPth[0], 
                        module.functions[objPth[0]].signature)
                elif __builtins__.has_key(objPth[0]):
                    return self.getFirstContinousBlock(
                          __builtins__[objPth[0]].__doc__)
                else:
                    return self.getFirstContinousBlock(
                           self.checkWxPyTips(module, objPth[0]))
                    
            if len(objPth) == 2 and objPth[0] == 'self':
                if cls.methods.has_key(objPth[1]):
                    return self.prepareModSigTip(objPth[1],
                          cls.methods[objPth[1]].signature)
                elif cls.super and type(cls.super[0]) is type(''):
                    return self.getFirstContinousBlock(
                      self.checkWxPyMethodTips(module, cls.super[0], objPth[1]))
                          
            if len(objPth) == 3 and objPth[0] == 'self':
                return self.getFirstContinousBlock(
                    self.getAttribSig(module, cls, objPth[1], objPth[2]))

            return ''

        else:
            if len(objPth) == 1:
                if module.functions.has_key(objPth[0]):
                    return self.prepareModSigTip(objPth[0], 
                        cls.functions[objPth[0]].signature)
                else:
                    return ''
        return ''

    def checkWxPyTips(self, module, name):
        if module.imports.has_key('wxPython.wx'):
            if wx.__dict__.has_key(name):
                t = type(wx.__dict__[name])
                if t is types.ClassType:
                    if wx.__dict__[name].__init__.__doc__:
                        return wx.__dict__[name].__init__.__doc__
        return ''

    def checkWxPyMethodTips(self, module, cls, name):
        if module.imports.has_key('wxPython.wx'):
            if wx.__dict__.has_key(cls):
                Cls = wx.__dict__[cls]
                if hasattr(Cls, name):
                    meth = getattr(Cls, name)
                    if meth.__doc__:
                        return meth.__doc__
        return ''

    def getAttribSig(self, module, cls, attrib, meth):
        if cls.attributes.has_key(attrib):
            objtype = cls.attributes[attrib][0].signature
            if module.classes.has_key(objtype) and \
                  module.classes[objtype].methods.has_key(meth):
                return module.classes[objtype].methods[meth].signature
            klass = wxNamespace.getWxClass(objtype)
            if klass:
                if hasattr(klass, meth):
                    return getattr(klass, meth).__doc__
        return ''

    def prepareModSigTip(self, name, paramsStr):
        if Utils.startswith(paramsStr, 'self,'):
            paramsStr = string.strip(paramsStr[5:])
        elif paramsStr == 'self':
            paramsStr = ''
        return '%s(%s)'%(name, paramsStr)

#---Code Completion-------------------------------------------------------------

    def getCodeCompOptions(self, word, rootWord, matchWord, lnNo):
        """ Overwritten Mixin method, returns list of code completion names """
        module = self.model.getModule()
        cls = module.getClassForLineNo(lnNo)
        if cls:
            objPth = string.split(rootWord, '.')

            if len(objPth) == 1:
                if objPth[0] == 'self':
                    return self.getAttribs(cls)
                if objPth[0] == '':
                    meth = cls.getMethodForLineNo(lnNo)
                    return self.getCodeNamespace(module, meth)
                else:
                    return []

            elif len(objPth) == 2 and objPth[0] == 'self':
                attrib = objPth[1]
                return self.getAttribAttribs(module, cls, attrib)

            else:
                return []
        else:
            func = module.getFunctionForLineNo(lnNo)
            return self.getCodeNamespace(module, func)

    def getWxAttribs(self, cls, mems = None):
        if mems is None: mems = []

        for base in cls.__bases__:
            self.getWxAttribs(base, mems)

        mems.extend(dir(cls))
        return mems

    def getAttribs(self, cls):
        loopCls = cls
        lst = []
        while loopCls:
            lst.extend(loopCls.methods.keys() + loopCls.attributes.keys())
            if len(loopCls.super):
                prnt = loopCls.super[0]
                # Modules
                if type(prnt) == type(self): # :)
                    loopCls = prnt
                # Possible wxPython ancestor
                else:
                    klass = wxNamespace.getWxClass(prnt)
                    if klass:
                        lst.extend(self.getWxAttribs(klass))
                    loopCls = None
            else:
                loopCls = None

        return lst

    typeMap = {'dict': dir({}), 'list': dir([]), 'string': dir(''),
               'tuple': dir(()), 'number': dir(0)}

    def getAttribAttribs(self, module, cls, attrib):
        if cls.attributes.has_key(attrib):
            objtype = cls.attributes[attrib][0].signature
            if self.typeMap.has_key(objtype):
                return self.typeMap[objtype]
            elif module.classes.has_key(objtype):
                return self.getAttribs(module.classes[objtype])
            else:
                klass = wxNamespace.getWxClass(objtype)
                if klass:
                    return self.getWxAttribs(klass)
        return []

    def getCodeNamespace(self, module, block):
        names = []
        
        names.extend(module.imports.keys())
        names.extend(module.class_order)
        names.extend(module.function_order)
        names.extend(module.global_order)
        names.extend(__builtins__.keys())
        
        if block: 
            names.extend(block.localnames())

        if module.imports.has_key('wxPython.wx'):
            return wxNamespace.getWxNameSpace() + names
        else:
            return names

#-------Browsing----------------------------------------------------------------
    def StyleVeto(self, style):
##        print 'STC: StyleVeto'
        return style != 11

    def BrowseClick(self, word, line, lineNo, start, style):
        """ Overridden from BrowseStyledTextCtrlMix, jumps to declaration or
            opens module

            Currently only the open module is inspected, classes declared
            outside the scope of the active module are inaccessible.
        """
        module = self.model.getModule()

        if self.model.editor.debugger and self.model.editor.debugger.isDebugBrowsing():
            self.model.editor.debugger.add_watch(word, true)
        elif line[start-5: start] == 'self.':
            cls = module.getClassForLineNo(lineNo)
            if cls:
                self.doClearBrwsLn()
                gotoLine = -1
                if cls.attributes.has_key(word):
                    gotoLine = cls.attributes[word][0].start-1
                elif cls.methods.has_key(word):
                    gotoLine = cls.methods[word].start-1
                else:
                    found, cls, block = module.find_declarer(cls, word, None)
                    if found:
                        if type(block) == type([]):
                            gotoLine = block[0].start-1
                        else:
                            gotoLine = block.start-1
                if gotoLine != -1:
                    self.model.editor.addBrowseMarker(lineNo)#self.GetCurrentLine())
                    self.GotoLine(gotoLine)
                return true
        # Imports
        elif module.imports.has_key(word):
            import imp
            self.doClearBrwsLn()
            try:
                srchpath = [os.path.dirname(self.model.filename)]
                if self.model.app:
                    srchpath.insert(0, os.path.dirname(self.model.app.filename))
                file, path, (ext, mode, tpe) = imp.find_module(word, srchpath)
            except ImportError:
                try:
                    file, path, (ext, mode, tpe) = imp.find_module(word)
                except ImportError:
                    return true

            path = os.path.abspath(path)
            if tpe == imp.PKG_DIRECTORY:
                self.model.editor.openOrGotoModule(os.path.join(path, '__init__.py'))
            elif tpe == imp.PY_SOURCE:
                self.model.editor.openOrGotoModule(path)

            return true

        # Classes
        elif module.classes.has_key(word):
            self.doClearBrwsLn()
            self.GotoLine(module.classes[word].block.start-1)
            return true
        # Global functions
        elif module.functions.has_key(word):
            self.doClearBrwsLn()
            self.GotoLine(module.functions[word].start-1)
            return true
        else:
            # Local names and parameters in methods and functions
            codeBlock = None
            cls = module.getClassForLineNo(lineNo)
            if cls:
                meth = cls.getMethodForLineNo(lineNo)
                if meth:
                    codeBlock = meth
            else:
                func = module.getFunctionForLineNo(lineNo)
                if func:
                    codeBlock = func
            if codeBlock:
                locals = codeBlock.localnames()
                if word in locals:
                    self.doClearBrwsLn()
                    if word in codeBlock.locals.keys():
                        self.GotoLine(codeBlock.locals[word].lineno-1)
                    else:
                        self.GotoLine(codeBlock.start-1)
                    return true

            # Global namespace including wxPython declarations
            if globals().has_key(word):
                self.doClearBrwsLn()
                obj = globals()[word]
                if hasattr(obj, '__init__'):
                    mod = self.model.editor.openOrGotoModule(obj.__init__.im_func.func_code.co_filename)
                    mod.views['Source'].GotoLine(obj.__init__.im_func.func_code.co_firstlineno -1)
                elif hasattr(obj, 'func_code'):
                    mod = self.model.editor.openOrGotoModule(obj.func_code.co_filename)
                    mod.views['Source'].GotoLine(obj.func_code.co_firstlineno -1)
                return true

    def goto(self, gotoLine):
        self.GotoLine(gotoLine)

    def underlineWord(self, start, length):
        start, length = BrowseStyledTextCtrlMix.underlineWord(self, start, length)
        if self.model.editor.debugger and self.model.editor.debugger.isDebugBrowsing():
            word, line, lnNo, wordStart = self.getStyledWordElems(start, length)
            self.IndicatorSetColour(0, wxRED)
            try:
                val = self.model.editor.debugger.getVarValue(word)
            except Exception, message:
                val = str(message)
            if val:
                self.model.editor.statusBar.setHint(val)
        else:
            self.IndicatorSetColour(0, wxBLUE)

        return start, length

    def getBrowsableText(self, line, piv, lnStPs):
        if self.model.editor.debugger and self.model.editor.debugger.isDebugBrowsing():
            return idWord(line, piv, lnStPs, object_delim)
        else:
            return BrowseStyledTextCtrlMix.getBrowsableText(self, line, piv, lnStPs)

#-------Debugger----------------------------------------------------------------
    def setInitialBreakpoints(self):
        for bp in self.breaks.values():
            self.MarkerAdd(bp.line -1, brkPtMrk)

    def setBdbBreakpoints(self):
        for bp in self.breaks.values():
            self.MarkerAdd(bp.line -1, brkPtMrk)

    def deleteBreakPoint(self, lineNo):
        if not self.breaks.has_key(lineNo):
            return

        bp = self.breaks[lineNo]
        if bp.temporary:
            self.MarkerDelete(lineNo - 1, tmpBrkPtMrk)
        else:
            self.MarkerDelete(lineNo - 1, brkPtMrk)

        if self.model.editor.debugger:
            bp = self.breaks[lineNo]
            res = self.model.editor.debugger.clear_break(bp.file, bp.line)
            if res: print res
            self.model.editor.debugger.breakpts.refreshList()
        else:
            self.breaks[lineNo].deleteMe()

        del self.breaks[lineNo]

    def addBreakPoint(self, lineNo, temp = 0):
        if wxPlatform == '__WXMSW__':
            filename = string.lower(self.model.filename)
        else:
            filename = self.model.filename

        if self.model.editor.debugger:
            bp = self.model.editor.debugger.set_breakpoint_here(\
                  filename, lineNo, temp)
        else:
            bp = bdb.Breakpoint(filename, lineNo, temp)

        if type(bp) == type(''):
            wxLogError(bp)
        else:
            self.breaks[lineNo] = bp

            if temp:
                mrk = tmpBrkPtMrk
            else:
                mrk = brkPtMrk
            hnd = self.MarkerAdd(lineNo - 1, mrk)


    def tryLoadBreakpoints(self):
        import pickle
        fn = self.getBreakpointFilename()
        update = false
        if os.path.exists(fn):
            self.breaks = pickle.load(open(fn))
            self.setInitialBreakpoints()
            BrkPt = bdb.Breakpoint
            for lineNo, brk in self.breaks.items():
                if self.model.editor.debugger:
                    self.model.editor.debugger.set_break(brk.file, lineNo)
                    update = true
                else:
                    BrkPt.bpbynumber.append(brk)
                    if BrkPt.bplist.has_key((brk.file, brk.line)):
                        BrkPt.bplist[brk.file, brk.line].append(brk)
                    else:
                        BrkPt.bplist[brk.file, brk.line] = [brk]
            if update:
                self.model.editor.debugger.breakpts.refreshList()

            return true
        else:
            self.breaks = {}
            return false

    def saveBreakpoints(self):
        # XXX This is not yet called automatically on saving a module, should it be ?
        import pickle
        fn = self.getBreakpointFilename()
        if len(self.breaks):
            pickle.dump(self.breaks, open(fn, 'w'))
        elif os.path.exists(fn):
            os.remove(fn)

    def setStepPos(self, lineNo):
        if self.stepPos != lineNo:
            if self.stepPos:
                self.MarkerDelete(self.stepPos, stepPosMrk)
            if lineNo:
                self.MarkerAdd(lineNo, stepPosMrk)
        self.stepPos = lineNo

    def getBreakpointFilename(self):
        return os.path.splitext(self.model.filename)[0]+'.brk'

    def disableSource(self, doDisable):
        self.SetReadOnly(doDisable)
        self.grayout(doDisable)

#---Syntax checking-------------------------------------------------------------

    def checkChangesAndSyntax(self, lineNo = None):
        """ Called before moving away from a line """
        if not Preferences.checkSyntax:
            return
        if lineNo is None:
            lineNo = self.GetCurrentLine()
        if not Preferences.onlyCheckIfLineModified or \
              lineNo == self.damagedLine:
            slb, sle = ( self.GetStyleAt(self.PositionFromLine(lineNo)),
                         self.GetStyleAt(self.GetLineEndPosition(lineNo)-1) )
            line = self.GetLine(lineNo)[:-1]
            ##import time
            ##t1 = time.time()
            self.checkSyntax( (line,), lineNo +1, self.GetLine,
                lineStartStyle = slb, lineEndStyle = sle)
            ##print time.time()-t1, 'synchecked'#, slb, sle, line

    def indicateError(self, lineNo, errOffset, errorHint):
        """ Underline the point of error at the given line """
        # Display red squigly indicator underneath error
        errPos = self.PositionFromLine(lineNo-1)
        lineLen = self.LineLength(lineNo-1)
        nextLineLen = self.LineLength(lineNo)
        lenAfterErr = lineLen-errOffset+1
        styleLen = min(3, lenAfterErr)

        self.StartStyling(errPos+errOffset-2, wxSTC_INDICS_MASK)
        self.SetStyling(styleLen, wxSTC_INDIC1_MASK)
        # XXX I have to set the styling past the cursor position, why????
        self.SetStyling(lenAfterErr+nextLineLen, 0)#wxSTC_INDIC0_MASK)

        if errorHint:
            self.model.editor.statusBar.setHint(errorHint, 'Error')

    def stripComment(self, line):
        segs = methodparse.safesplitfields(line, '#')
        if len(segs) > 1:
            line = segs[0] + ' '*(len(line)-len(segs[0])-1)+'\n'

        return line

    if_keywords = {'else':    'if 1',
                   'elif':    'if  ',
                  }
    try_keywords = {'except':  'try:pass',
                    'finally': 'try:pass',
                   }

    line_conts = ('(', '[', '{', '\\', ',')
    line_conts_ends = (')', ']', '}', ':', ',', '%')

    # Multiline strings, ignored currently
    ignore_styles = {6 : "'''", 7 : '"""'}

    syntax_errors = ('invalid syntax', 'invalid token')

    def checkSyntax(self, prevlines, lineNo, getPrevLine, compprefix = '', indent = '', contLinesOffset = 0, lineStartStyle = 0, lineEndStyle = 0):
        # XXX Should also check syntax before saving.
        # XXX Multiline without brackets not caught
        # XXX Should check indent errors (multilines make this tricky)

        # XXX Unhandled cases:
        # XXX     ZopeCompanions 278
        # XXX     print a, b,
        # XXX         c, d
        errstr = 'Line %d valid '%lineNo
        prevline = prevlines[-1]
        stripprevline = string.strip(prevline)

        # Special case for blank lines
        if not stripprevline:
            self.model.editor.statusBar.setHint(errstr)
            return

        # Ignore multiline strings
        if lineStartStyle in self.ignore_styles.keys() or \
              lineEndStyle in self.ignore_styles.keys():
            self.model.editor.statusBar.setHint(errstr)
            return

        # Special case for \ followed by whitespace (don't strip it!)
        compstr = ''
        if stripprevline[-1] == '\\' and not compprefix:
            strs = string.split(prevline, '\\')
            if strs[-1] and not string.strip(strs[-1]):
                compstr = string.lstrip(prevline)

        # note, removes (flattens) indent
        if not compstr:
            compstr = compprefix+string.join(\
                  map(lambda line, indent=indent: indent+string.strip(line),
                  prevlines), '\n')+'\n'
        try:
            compile(compstr, '<editor>', 'single')
#        except IndentationError, err:
        except SyntaxError, err:
            err.lineno = lineNo
            errstr = err.__class__.__name__+': '+str(err)
            indentpl = string.find(prevline, stripprevline)
            if err[0] == 'unexpected EOF while parsing':
                errstr = 'incomplete (%d)'%lineNo
            elif err[0] == "'return' outside function":
                self.checkSyntax(prevlines, lineNo, getPrevLine,
                      'def func():\n', ' ')
                return
            elif err[0] == 'expected an indented block':
                errstr = errstr + ' ignored'
                ##print prevlines, lineNo, getPrevLine
            elif err[0] in ("'break' outside loop",
                  "'continue' not properly in loop"):
                self.checkSyntax(prevlines, lineNo, getPrevLine,
                      'while 1:\n', ' ')
                return
            elif err[0] == 'invalid token':
                self.indicateError(lineNo,
                      err.offset + indentpl - len(indent) - contLinesOffset,
                      'SyntaxError: %s'%err[0])

            # Invalid syntax
            else:
                # XXX remove !
##                if err[0] == "can't assign to literal":
##                    # XXX This error causes infinite recursion, skip for now
##                    return
                if len(prevlines) == 1 and err.offset is not None and not contLinesOffset:
                    # Check for dedenting keywords
                    possblkeyword = stripprevline[:err.offset-len(indent)]
                    if possblkeyword in self.if_keywords.keys():
                        self.checkSyntax( (string.replace(prevline,
                            possblkeyword, self.if_keywords[possblkeyword], 1),),
                            lineNo, getPrevLine)
                        return
                    elif possblkeyword in self.try_keywords.keys():
                        if stripprevline[-1] == ':':
                            prevline = string.rstrip(prevline)+'pass\n'

                        self.checkSyntax( (self.try_keywords[possblkeyword],
                                           prevline), lineNo, getPrevLine)
                        return

                    # Check for line continueations
                    # XXX Lines ending on line_conts should be ignored
                    errpos = err.offset-len(indent)-1
                    if errpos < len(stripprevline) and \
                          stripprevline[errpos] in self.line_conts_ends:
                        ln = lineNo - 2

                        if stripprevline[-1] == '\\':
                            lines = string.rstrip(prevline)[:-1]+' '
                        else:
                            lines = string.rstrip(prevline)

                        errOffsetOffset = 0
                        while ln >= 0:
                            line = self.stripComment(getPrevLine(ln)[:-1])

                            rstripline = string.rstrip(line)
                            if rstripline and rstripline[-1] in self.line_conts:
                                # replace else, elif's with ifs
                                lstripline = string.lstrip(line)
                                if len(lstripline) >= 4:
                                    possblifkeyword = lstripline[:4]
                                    if possblifkeyword in self.if_keywords.keys():
                                        ##print 'replace if kw'
                                        rstripline = string.replace(rstripline,
                                              possblifkeyword,
                                              self.if_keywords[possblifkeyword], 1)

                                if rstripline[-1] == '\\':
                                    lines = rstripline[:-1] +' '+ lines
                                else:
                                    lines = rstripline + lines
                                errOffsetOffset = errOffsetOffset + len(rstripline)
                                ln = ln -1
                            else:
                                break

                        if ln < lineNo - 2:
                            self.checkSyntax((lines,), lineNo, getPrevLine,
                                  contLinesOffset = errOffsetOffset)
                            return

                if not err.offset:
                    erroffset = 0
                else:
                    erroffset = err.offset

                self.indicateError(lineNo, 
                    erroffset + indentpl - len(indent) - contLinesOffset,
                    errstr)
                self.damagedLine = -1
                return

        except Exception, err:
            errstr = err.__class__.__name__+': '+str(err)

        if errstr:
            self.model.editor.statusBar.setHint(errstr)

        self.damagedLine = -1

#-------Events------------------------------------------------------------------
    def OnMarginClick(self, event):
        if event.GetMargin() == 1:
            lineClicked = self.GetLineFromPos(event.GetPosition()) + 1
            if self.breaks.has_key(lineClicked):
                self.deleteBreakPoint(lineClicked)
            else:
                self.addBreakPoint(lineClicked)
        else:
            FoldingStyledTextCtrlMix.OnMarginClick(self, event)

    def OnSetBreakPoint(self, event):
        line = self.GetLineFromPos(self.GetCurrentPos()) + 1
        if self.breaks.has_key(line):
            self.deleteBreakPoint(line)
        else:
            self.addBreakPoint(line)

    def OnRunToCursor(self, event):
        line = self.GetLineFromPos(self.GetCurrentPos()) + 1
        if not self.breaks.has_key(line):
            self.addBreakPoint(line, 1)
        if self.model.defaultName == 'App':
            self.model.editor.debugger.debug_file(self.model.filename)
        elif self.model.app:
            self.model.editor.debugger.debug_file(self.model.app.filename)
#        else return
        # XXX Case where module is run, outside app

    def OnRun(self, event):
        if not self.model.savedAs: #modified or len(self.model.viewsModified):
            wxMessageBox('Cannot run an unsaved module.')
            return
        self.model.run()

    def OnRunParams(self, event):
        if not self.model.savedAs: #modified or len(self.model.viewsModified):
            wxMessageBox('Cannot run an unsaved module.')
            return
        dlg = wxTextEntryDialog(self.model.editor, 'Parameters:',
          'Run with parameters', self.lastRunParams)
        try:
            if dlg.ShowModal() == wxID_OK:
                self.lastRunParams = dlg.GetValue()
                self.model.run(self.lastRunParams)
        finally:
            dlg.Destroy()

    def OnRunApp(self, event):
        if not self.model.app.savedAs: #modified or len(self.model.viewsModified):
            wxMessageBox('Cannot run an unsaved application.')
            return
        wxBeginBusyCursor()
        try:
            self.model.app.run()
        finally:
            wxEndBusyCursor()

    def OnDebug(self, event):
        if not self.model.savedAs or self.model.modified or \
          len(self.model.viewsModified):
            wxMessageBox('Cannot debug an unsaved or modified module.')
            return
        self.model.debug()

    def OnDebugParams(self, event):
        if not self.model.savedAs or self.model.modified or \
          len(self.model.viewsModified):
            wxMessageBox('Cannot debug an unsaved or modified module.')
            return
        dlg = wxTextEntryDialog(self.model.editor, 'Parameters:',
          'Debug with parameters', self.lastDebugParams)
        try:
            if dlg.ShowModal() == wxID_OK:
                self.lastDebugParams = dlg.GetValue()
                self.model.debug(methodparse.safesplitfields(self.lastDebugParams, ' '))
        finally:
            dlg.Destroy()

    def OnDebugStepIn(self, event):
        if self.model.editor.debugger:
            self.model.editor.debugger.OnStep(event)

    def OnDebugStepOver(self, event):
        if self.model.editor.debugger:
            self.model.editor.debugger.OnOver(event)

    def OnDebugStepOut(self, event):
        if self.model.editor.debugger:
            self.model.editor.debugger.OnOut(event)

    def OnCompile(self, event):
        if not self.model.savedAs or self.model.modified or \
          len(self.model.viewsModified):
            wxMessageBox('Cannot compile an unsaved or modified module.')
            return
        self.model.compile()

    def OnProfile(self, event):
        stats, profDir = self.model.profile()
        resName = 'Profile stats'
        if not self.model.views.has_key(resName):
            resultView = self.model.editor.addNewView(resName,
              ProfileView.ProfileStatsView)
        else:
            resultView = self.model.views[resName]
        resultView.tabName = resName
        resultView.stats = stats
        resultView.profDir = profDir
        resultView.refresh()
        resultView.focus()

    def OnContextHelp(self, event):
        pos = self.GetCurrentPos()
        lnNo = self.GetCurrentLine()
        lnStPs = self.GetLineStartPos(lnNo)
        line = self.GetCurrentLineText()[0]
        piv = pos - lnStPs
        start, length = idWord(line, piv, lnStPs)
        startLine = start-lnStPs
        word = line[startLine:startLine+length]
        Help.showContextHelp(self.model.editor, self.model.editor.palette.toolBar, word)

    def OnComment(self, event):
        self.processSelectionBlock(self.processComment)

    def OnUnComment(self, event):
        self.processSelectionBlock(self.processUncomment)

    def OnIndent(self, event):
        selStartPos, selEndPos = self.GetSelection()
        if selStartPos != selEndPos:
            self.processSelectionBlock(self.processIndent)
        else:
            self.AddText(indentLevel*' ')

    def OnDedent(self, event):
        selStartPos, selEndPos = self.GetSelection()
        if selStartPos != selEndPos:
            self.processSelectionBlock(self.processDedent)
        elif self.GetTextRange(selStartPos - indentLevel, selStartPos) == indentLevel*' ':
            self.SetSelection(selStartPos - indentLevel, selStartPos)
            self.ReplaceSelection('')

    def OnAddSimpleApp(self, event):
        self.BeginUndoAction()
        try:
            self.InsertText(self.GetTextLength(), self.model.getSimpleRunnerSrc())
        finally:
            self.EndUndoAction()

    def OnStyle(self, event):
        pass

    def OnAddModuleInfo(self, event):
        self.refreshModel()
        prefs = Preferences.staticInfoPrefs.copy()
        self.model.addModuleInfo(prefs)
        self.updateEditor()

    def OnUpdateUI(self, event):
        ## This event handler may be disabled (execption handler allows
        ## for the case where the flag is not defined.
        try:
            if self.NoUpdateUI == 1:
                return
        except:
            pass
        # don't update if not fully initialised
        if hasattr(self, 'pageIdx'):
            self.updateViewState()

        if Preferences.braceHighLight:
            PythonStyledTextCtrlMix.OnUpdateUI(self, event)

    def OnAddChar(self, event):
        char = event.GetKey()
        # On enter indent to same indentation as line above
        # If ends in : indent xtra block
        lineNo = self.GetCurrentLine()
        self.damagedLine = lineNo
        if char == 10:
            pos = self.GetCurrentPos()
            # XXX GetLine returns garbage in the last char
            prevline = self.GetLine(lineNo -1)[:-1]
            
            self.doAutoIndent(prevline, pos)

            self.damagedLine = lineNo-1
            self.checkChangesAndSyntax(lineNo-1)

    def OnKeyDown(self, event):
        if self.CallTipActive():
            self.callTipCheck()

        key = event.KeyCode()

        # thx to Robert Boulanger
        if Preferences.handleSpecialEuropeanKeys:
            self.handleSpecialEuropeanKeys(event)

        if key in (WXK_UP, WXK_DOWN):
            self.checkChangesAndSyntax()
        # Tabbed indent
        elif key == 9:
            self.AddText(indentLevel*' ')
            self.damagedLine = self.GetCurrentLine()
            if not self.AutoCompActive(): return
        # Smart delete
        elif key == 8:
            line = self.GetCurrentLineText()
            if len(line): line = line[0]
            else: line = ''
            pos = self.GetCurrentPos()
            self.damagedLine = self.GetLineFromPos(pos)
            #ignore indenting when at start of line
            if self.GetLineStartPos(self.GetLineFromPos(pos)) != pos:
                pos = pos -1
                ln = self.GetLineFromPos(pos)
                ls = self.GetLineStartPos(ln)
                st = pos - ls
                if not string.strip(line[:st]):
                    self.SetSelection(ls + st/4*4, pos+1)
                    self.ReplaceSelection('')
                    return
        #event.Skip()
        BrowseStyledTextCtrlMix.OnKeyDown(self, event)

#---Meta comment----------------------------------------------------------------
    def OnAddCommentLine(self, event):
        pos = self.GetCurrentPos()
        ln = self.GetLineFromPos(pos)
        ls = self.GetLineStartPos(ln)
        self.InsertText(ls, '#-------------------------------------------'
                                    '------------------------------------'+'\n')
        self.SetCurrentPosition(ls+4)

    def OnViewWhitespace(self, event):
        miid = self.menu.FindItem('View whitespace')
        if self.menu.IsChecked(miid):
            mode = wxSTC_WS_INVISIBLE
            self.menu.Check(miid, false)
        else:
            mode = wxSTC_WS_VISIBLEALWAYS
            self.menu.Check(miid, true)

        self.SetViewWhiteSpace(mode)
#        self.menu.Check(miid, not self.menu.IsChecked(miid))

    def OnViewEOL(self, event):
        miid = self.menu.FindItem('View EOL characters')
        check = not self.menu.IsChecked(miid)
        self.menu.Check(miid, check)
        self.SetViewEOL(check)

    def OnSaveBreakPoints(self, event):
        self.saveBreakpoints()

    def OnLoadBreakPoints(self, event):
        self.tryLoadBreakpoints()

    def OnAddClassAtCursor(self, event):
        pos = self.GetCurrentPos()
        lnNo = self.GetCurrentLine()
        lnStPs = self.GetLineStartPos(lnNo)
        line = self.GetLine(lnNo)#self.GetCurrentLineText()[0]
        piv = pos - lnStPs
        start, length = idWord(line, piv, lnStPs, object_delim)
        startLine = start-lnStPs
        word = line[startLine:startLine+length]
        # 1st Xform; Add method at cursor to the class
        if Utils.startswith(word, 'self.'):
            methName = word[5:]
            # Apply if there are changes to views
            self.model.refreshFromViews()
            module = self.model.getModule()
            cls = module.getClassForLineNo(lnNo)
            if not cls.methods.has_key(methName):
                # Check if it looks like an event
                if len(methName) > 2 and methName[:2] == 'On' and (methName[2]
                                                       in string.uppercase+'_'):
                    parms = 'self, event'
                else:
                    parms = 'self, '

                module.addMethod(cls.name, methName, parms, ['        pass'], true)
                if cls.methods.has_key(methName):
                    lnNo = cls.methods[methName].start+2
                    self.model.refreshFromModule()
                    self.model.modified = true
                    self.model.editor.updateModulePage(self.model)
                    line2pos = self.PositionFromLine(lnNo)
                    self.SetCurrentPos(line2pos+8)
                    self.SetSelection(line2pos+8, line2pos+12)
                else:
                    print 'Method was not added'
        else:
            # 2nd Xform; Add inherited method call underneath method declation
            #            at cursor
            if string.strip(line[:startLine]) == 'def':
                self.model.refreshFromViews()
                module = self.model.getModule()
                cls = module.getClassForLineNo(lnNo)
                if cls.super:
                    base1 = cls.super[0]
                    if type(base1) is type(''):
                        baseName = base1
                    else:
                        baseName = base1.name
                    meth = cls.getMethodForLineNo(lnNo+1)
                    module.addLine('%s%s.%s(%s)'%(' '*startLine, baseName,
                          word, meth.signature), lnNo+1)
                    self.model.refreshFromModule()
                    self.model.modified = true
                    self.model.editor.updateModulePage(self.model)




    def OnReindent(self, event):
        self.model.reindent()

    def OnRefresh(self, event):
        if Preferences.autoReindent:
            self.model.reindent(false)
        EditorStyledTextCtrl.OnRefresh(self, event)

    def OnModified(self, event):
        modType = event.GetModificationType()
        if modType == (wxSTC_MOD_CHANGEMARKER):
            pass#print 'marker change'
        linesAdded = event.GetLinesAdded()
        # module has to have been parsed at least once
        if linesAdded and self.model._module:
            lineNo = self.LineFromPosition(event.GetPosition())
            module = self.model.getModule()
            module.renumber(linesAdded, lineNo)

    def OnCompleteCode(self, event):
        self.codeCompCheck()

    def OnParamTips(self, event):
        self.callTipCheck()
