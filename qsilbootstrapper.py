#!/usr/bin/env python3

from qsilInterpreter import Object, Pointer, Interpreter, Bytecode, SpecialIDs, VisibilityTypes, QSIL_TYPE_DIRECTOBJECT, QSIL_TYPE_DIRECTPOINTEROBJECT
from struct import pack

printBytecodes = False

classClassInstVars = []
methodClassInstVars = []
bootstrapPtr = None

class QSILClass(object):
    def __init__(self):
        self.name = b'Object'
        self.type = b'subclass:'
        self.superclass = b'Object'
        self.classId = 0
        self.instancevariables = []
        self.classvariables = []
        self.methods = []

    def __repr__(self):
        return f'[class {self.name.decode("utf-8")}, methods: {self.methods}]'

    def asQSILObject(self, parser):
        global classClassInstVars
        ret = Object()
        ret.classId = SpecialIDs.CLASS_CLASS_ID
        ret.objId = self.classId
        serializedInstVars = []
        classClassInstVars = classClassInstVars or parser.classes[b"Class"].instancevariables
        for var in classClassInstVars:
            #print(var)
            if var == b'type':
                serializedInstVars.append(parser.qsilStringPtr(self.type))
            elif var == b'className':
                serializedInstVars.append(parser.qsilStringPtr(self.name))
            elif var == b'superclass':
                ptr = Pointer()
                if self.superclass == self.name:
                    ptr.objId = ret.objId
                else:
                    ptr.objId = parser.classes[self.superclass].objId
                serializedInstVars.append(ptr)
            elif var == b'instVarNames':
                if self.superclass == self.name:
                    varNames = []
                else:
                    superclass = parser.classes[self.superclass].pyObjStorage[3]
                    superclassInstVars = parser.objects[superclass.objId].pyObjStorage
                    varNames = [x for x in superclassInstVars]
                varNames += [parser.qsilStringPtr(varName) for varName in self.instancevariables]
                serializedInstVars.append(parser.qsilOrderedCollectionPtr(varNames))
            elif var == b'classVarNames':
                varNames = [parser.qsilStringPtr(varName) for varName in self.classvariables]
                serializedInstVars.append(parser.qsilOrderedCollectionPtr(varNames))
            elif var == b'methods':
                serializedMethods = []
                for method in self.methods:
                    serializedMethods.append(method.asQSILObject(parser))
                serializedInstVars.append(parser.qsilOrderedCollectionPtr(serializedMethods))
            else:
                print(var)
                serializedInstVars.append(parser.qsilNumberPtr(0))

        ret.setMem(serializedInstVars)

        parser.objects[ret.objId] = ret
        parser.classes[self.name] = ret


class QSILMethod(object):
    def __init__(self):
        self.name = b''
        self.visibility = []
        self.args = []
        self.bytecodes = b''
        self.literalPtrs = []
        self.objId = 0
        self.numTemps = 0
        self._class = None

    def __repr__(self):
        return b' '.join(self.visibility).decode('utf-8') + ' #' + self.name.decode('utf-8')

    def asQSILObject(self, parser):
        global methodClassInstVars
        ret = Object()
        ret.classId = SpecialIDs.METHOD_CLASS_ID
        ret.objId = self.objId
        serializedInstVars = []
        methodClassInstVars = methodClassInstVars or parser.classes[b"Method"].instancevariables
        for var in methodClassInstVars:
            if var == b'methodName':
                serializedInstVars.append(parser.qsilStringPtr(self.name))
            elif var == b'visibility':
                visibilityNum = 0
                if b'private' in self.visibility:
                    visibilityNum |= VisibilityTypes.PRIVATE
                if b'protected' in self.visibility:
                    visibilityNum |= VisibilityTypes.PROTECTED
                if b'public' in self.visibility:
                    visibilityNum &= 0b1
                if b'static' in self.visibility:
                    visibilityNum |= VisibilityTypes.STATIC
                serializedInstVars.append(parser.qsilNumberPtr(visibilityNum))
            elif var == b'args':
                serializedInstVars.append(parser.qsilNumberPtr(len(self.args)))
            elif var == b'bytecodes':
                finalBytecodes = b''
                for bc in self.bytecodes:
                    if isinstance(bc, bytes):
                        finalBytecodes += bc
                    else:
                        finalBytecodes += bytes([bc])
                serializedInstVars.append(parser.qsilStringPtr(finalBytecodes))
            elif var == b'literals':
                serializedInstVars.append(parser.qsilOrderedCollectionPtr(self.literalPtrs))
            elif var == b'numTemps':
                print("At some point, this should be implemented. It's kinda important ish")
            elif var == b'class':
                ptr = Pointer()
                ptr.objId = self._class
                serializedInstVars.append(ptr)
            else:
                print(var)
                serializedInstVars.append(parser.qsilNumberPtr(0))

        ret.setMem(serializedInstVars)

        parser.objects[ret.objId] = ret
        return Pointer.forObject(ret)

specials = [b'+', b',' b'-', b'/', b'*', b'>',
            b'<', b'<=',b'>=', b'=', b'~=', b'==',
            b'~==', b'&&', b'||', b'\\']


class Parser(object):
    def __init__(self, infile):
        self.stream = infile
        self.objects = {}
        self.blockContexts = []
        self.currObjectId = SpecialIDs.numObjs
        self.classes = {}

    def peek(self, length=1):
        pos = self.stream.tell()
        ret = self.stream.read(length)
        self.stream.seek(pos)
        return ret
    
    def skipwhitespace(self):
        while self.peek() in b' \t\r\n':
            self.stream.read(1)

    def readToken(self):
        tok = b''
        self.skipwhitespace()
        if self.peek() in b')].':
            return self.stream.read(1)
        while self.peek() not in b' \t\r\n)].':
            tok += self.stream.read(1)
        return tok
    
    def peekToken(self, num = 1):
        pos = self.stream.tell()
        ret = self.readToken()
        if num > 1:
            ret = [ret]
            for _ in range(num - 1):
                ret.append(self.readToken())
        self.stream.seek(pos)
        return ret

    def readString(self):
        string = b''
        self.skipwhitespace()
        assert self.stream.read(1) == b'\''
        while True:
            # Lazy, but we're assuming all strings have been terminated
            char = self.stream.read(1)
            if char == b'\'':
                if self.peek() == b'\'':
                    self.stream.read(1) # Consume one
                else:
                    break
            string += char
        return string

    def nextObjectId(self):
        ret = self.currObjectId
        self.currObjectId += 1
        return ret

    def qsilStringPtr(self, string):
        qsilString = Object()
        qsilString.classId = SpecialIDs.BYTESTRING_CLASS_ID
        qsilString.type = QSIL_TYPE_DIRECTOBJECT
        qsilString.setMem(string)
        qsilString.objId = self.nextObjectId()
        self.objects[qsilString.objId] = qsilString

        return Pointer.forObject(qsilString)

    def qsilSymbolPtr(self, string):
        qsilSymbol = Object()
        qsilSymbol.classId = SpecialIDs.SYMBOL_CLASS_ID
        qsilSymbol.type = QSIL_TYPE_DIRECTOBJECT
        qsilSymbol.setMem(string)
        qsilSymbol.objId = self.nextObjectId()
        self.objects[qsilSymbol.objId] = qsilSymbol

        return Pointer.forObject(qsilSymbol)

    def qsilCharacterPtr(self, char):
        qsilCharacter = Object()
        qsilCharacter.classId = SpecialIDs.CHARACTER_CLASS_ID
        qsilCharacter.type = QSIL_TYPE_DIRECTOBJECT
        qsilCharacter.setMem(bytes([char]))
        qsilCharacter.objId = self.nextObjectId()
        self.objects[qsilCharacter.objId] = qsilCharacter

        return Pointer.forObject(qsilCharacter)

    def qsilNumberPtr(self, num):
        qsilNumber = Object()
        qsilNumber.classId = SpecialIDs.INTEGER_CLASS_ID if isinstance(num, int) else SpecialIDs.FLOAT_CLASS_ID
        qsilNumber.type = QSIL_TYPE_DIRECTOBJECT
        numToBytes = pack("<i", num)
        qsilNumber.setMem(numToBytes)
        qsilNumber.objId = self.nextObjectId()
        self.objects[qsilNumber.objId] = qsilNumber

        return Pointer.forObject(qsilNumber)

    def qsilOrderedCollectionPtr(self, objects):
        qsilOrderedCollection = Object()
        qsilOrderedCollection.classId = SpecialIDs.ORDEREDCOLLECTION_CLASS_ID
        qsilOrderedCollection.type = QSIL_TYPE_DIRECTPOINTEROBJECT
        qsilOrderedCollection.setMem(objects)
        qsilOrderedCollection.objId = self.nextObjectId()
        self.objects[qsilOrderedCollection.objId] = qsilOrderedCollection

        return Pointer.forObject(qsilOrderedCollection)

    def qsilBlockContextPtr(self, bytecodes, newliterals, methodargs):
        qsilBlockContext = Object()
        qsilBlockContext.classId = SpecialIDs.BLOCKCONTEXT_CLASS_ID

        pcPtr = self.qsilNumberPtr(0)
        stackPtr = self.qsilOrderedCollectionPtr([])
        receiverPtr = Pointer()
        receiverPtr.objId = SpecialIDs.NIL_OBJECT_ID
        tempvarsPtr = self.qsilOrderedCollectionPtr([])
        argsPtr = self.qsilOrderedCollectionPtr([])
        parentContextPtr = Pointer()
        parentContextPtr.objId = SpecialIDs.NIL_OBJECT_ID
        bytecodesPtr = self.qsilStringPtr(bytecodes)
        literalsPtr = self.qsilOrderedCollectionPtr(newliterals)
        homePtr = parentContextPtr

        bcMem = [pcPtr, stackPtr, receiverPtr, tempvarsPtr, parentContextPtr, argsPtr, literalsPtr, bytecodesPtr, homePtr]
        qsilBlockContext.setMem(bcMem)
        qsilBlockContext.objId = self.nextObjectId()
        self.objects[qsilBlockContext.objId] = qsilBlockContext

        self.blockContexts.append(qsilBlockContext)

        return Pointer.forObject(qsilBlockContext)

    def pointerToLiteralOrderedCollection(self):
        self.skipwhitespace()
        assert self.stream.read(2) == b'#('
        objs = []
        tok = self.peekToken()
        while tok != b')':
            if tok.startswith(b'\''):
                strVal = self.readString()
                objs.append(self.qsilStringPtr(strVal))
            elif tok.startswith(b'#'):
                if tok.startswith(b'#('):
                    objs.append(self.pointerToLiteralOrderedCollection())
                else:
                    symbVal = self.readToken()[1:]
                    objs.append(self.qsilSymbolPtr(symbVal))
            elif tok.startswith(b'$'):
                self.stream.read(1)
                objs.append(self.qsilCharacterPtr(self.stream.read(1)))
            elif tok.startswith(b'"'):
                self.consumeComment()
            else:
                if (tok[0:1].isupper() or tok[0:1].islower()):
                    objs.append(['latebindliteral', self.readToken()])
                else:
                    if b'.' in self.peekToken(2)[1]:
                        numVal = float(b''.join(self.peekToken(3)))
                        self.readToken()
                        self.readToken()
                        self.readToken()
                    else:
                        numVal = int(self.readToken())
                    objs.append(self.qsilNumberPtr(numVal))
            tok = self.peekToken()
        self.skipwhitespace()
        self.stream.read(1)
        
        return self.qsilOrderedCollectionPtr(objs)

    def consumeComment(self):
        self.skipwhitespace()
        if self.peek() == b'"':
            self.stream.read(1)
            while self.peek() != b'"':
                self.stream.read(1)
            self.stream.read(1)

    def methodToBytecodes(self, methodargs, addReturn = True, declaredVariables = None, literalPtrs = None):
        bytecodes = []
        declaredVariables = declaredVariables or []
        numTemps = [0]
        literalPtrs = literalPtrs or []
        if literalPtrs:
            literals = [None for _ in literalPtrs]
        else:
            literals = []
        def readObject():
            tok = self.peekToken()
            if tok in [b'true', b'false', b'self', b'super', b'nil']:
                if tok == b'true':
                    bytecodes.append(Bytecode.PUSH_TRUE)
                elif tok == b'false':
                    bytecodes.append(Bytecode.PUSH_FALSE)
                elif tok == b'self':
                    bytecodes.append(Bytecode.PUSH_SELF)
                elif tok == b'super':
                    bytecodes.append(Bytecode.PUSH_SUPER)
                elif tok == b'nil':
                    bytecodes.append(Bytecode.PUSH_NIL)
                self.readToken()
            elif tok in declaredVariables:
                # Push tempvar by index onto the stack
                index = declaredVariables.index(tok)
                bytecodes.append(Bytecode.PUSH_TEMP) # pushTemp:
                bytecodes.append(bytes([index]))
                self.readToken()
            elif tok in methodargs:
                index = methodargs.index(tok)
                bytecodes.append(Bytecode.PUSH_ARG) # pushArg:
                bytecodes.append(bytes([index]))
                self.readToken()
            elif tok.startswith(b'#'):
                # Either an OrderedCollection or symbol
                if tok.startswith(b'#('):
                    literals.append(None)
                    literalPtrs.append(self.pointerToLiteralOrderedCollection())
                    ptrVal = len(literals) - 1
                else:
                    symbVal = self.readToken()[1:]
                    if symbVal in literals:
                        ptrVal = literals.index(symbVal)
                    else:
                        literalPtrs.append(self.qsilSymbolPtr(symbVal))
                        literals.append(symbVal)
                        ptrVal = len(literals) - 1
                bytecodes.append(Bytecode.PUSH_LITERAL) # PUSH_LITERAL
                bytecodes.append(bytes([ptrVal]))
                #print(bytecodes, literals)
            elif tok.startswith(b'\''):
                strVal = self.readString()
                if strVal in literals:
                    strPtr = literals.index(strVal)
                else:
                    literalPtrs.append(self.qsilStringPtr(strVal))
                    literals.append(strVal)
                    strPtr = len(literals) - 1
                bytecodes.append(Bytecode.PUSH_LITERAL) # PUSH_LITERAL
                bytecodes.append(bytes([strPtr]))
                #print(bytecodes, literals)
            elif tok.startswith(b'('):
                self.skipwhitespace()
                self.stream.read(1)
                bytecodeOneLine()
                self.skipwhitespace()
                assert self.stream.read(1) == b')'
            elif tok.startswith(b'['):
                self.skipwhitespace()
                self.stream.read(1)
                argNames = []
                while self.peekToken().startswith(b':'):
                    # Arguments to this block
                    argNames.append(self.readToken()[1:])
                if argNames:
                    assert self.readToken() == b'|'
                bc, newliterals = self.methodToBytecodes(methodargs + argNames, False, declaredVariables[:], literalPtrs[:])
                ctxPtr = self.qsilBlockContextPtr(bc, newliterals, methodargs)

                literalPtrs.append(ctxPtr)
                literals.append(None)

                self.skipwhitespace()
                bytecodes.append(Bytecode.PUSH_LITERAL) # PUSH_LITERAL
                bytecodes.append(bytes([len(literals) - 1]))
                assert self.stream.read(1) == b']'
            else:
                # Try to read an integer or float, or if that fails, assume it's
                # a class name
                if (tok[0:1].isupper() or tok[0:1].islower()):
                    bytecodes.append(['latebindliteral', self.readToken()])
                else:
                    if b'.' in self.peekToken(2)[1]:
                        numVal = float(b''.join(self.peekToken(3)))
                        self.readToken()
                        self.readToken()
                        self.readToken()
                    else:
                        numVal = int(self.readToken())
                    if numVal in literals:
                        numPtr = literals.index(numVal)
                    else:
                        literalPtrs.append(self.qsilNumberPtr(numVal))
                        literals.append(numVal)
                        numPtr = len(literals) - 1
                    bytecodes.append(Bytecode.PUSH_LITERAL) # PUSH_LITERAL
                    bytecodes.append(bytes([numPtr]))

        def readSelector(canHaveArgs):
            self.skipwhitespace()
            if self.peek() in [b')', b'.', b']']:
                return # No selector, just have a literal or something
            selName = self.peekToken()
            if not canHaveArgs:
                if ((selName.endswith(b':') or
            selName in specials)):
                    return
            self.readToken()
            while canHaveArgs:
                if (selName.endswith(b':') or selName in specials):
                    readObject()
                    readSelector(False)
                if selName in specials or (not selName.endswith(b':')):
                    break
                while self.peekToken().endswith(b':'):
                    selName += self.readToken()
                    bytecodeOneLine(False)
                break

            # Push a call for ourselves onto the stack
            #print("Got here")
            if selName in literals:
                ptrVal = literals.index(selName)
            else:
                literalPtrs.append(self.qsilSymbolPtr(selName))
                literals.append(selName)
                ptrVal = len(literals) - 1
            bytecodes.append(Bytecode.PUSH_LITERAL)
            bytecodes.append(bytes([ptrVal]))
            bytecodes.append(Bytecode.CALL)

            #print(bytecodes)

        def bytecodeOneLine(canHaveArgs = True, popAfterwards = True):
            # Read an initial object
            while self.peekToken().startswith(b'"'):
                self.consumeComment()
            if self.peekToken(2)[1] == b':=':
                # Read the rvalue and then push a bytecode to write by index
                if self.peekToken() in declaredVariables:
                    varIndex = declaredVariables.index(self.readToken())
                    self.readToken() # Consume := symbol
                    bytecodeOneLine(canHaveArgs, False)
                    bytecodes.append(Bytecode.POP_INTO_TEMP) # popIntoTemp:
                    bytecodes.append(bytes([varIndex]))
                else:
                    # Another late bind, this time as an lvalue
                    lvalueName = self.readToken()
                    self.readToken() # Consume := symbol
                    bytecodeOneLine(canHaveArgs, False)
                    bytecodes.append(['latebindlvalue', lvalueName])
                if self.peekToken() == b'.':
                    self.readToken()
                    if popAfterwards:
                        bytecodes.append(Bytecode.POP) # POP

                return
            if self.peekToken().startswith(b'^'):
                self.skipwhitespace()
                self.stream.read(1)
                bytecodeOneLine()
                bytecodes.append(Bytecode.RETURN) # RETURN
            elif self.peekToken() == b'|':
                # Read tempvars
                varNames = b''
                self.readToken()
                while self.peek() != b'|':
                    varNames += self.stream.read(1)
                self.stream.read(1)
                newVars = [x for x in varNames.strip().split(b' ') if x]
                numTemps[0] += len(newVars)
                declaredVariables.extend(newVars)
            elif self.peekToken() != b']':
                readObject()
                self.consumeComment()
                while self.peekToken() not in [b')', b']']:
                    self.consumeComment()
                    readSelector(canHaveArgs)
                    self.consumeComment()
                    if self.peekToken() == b'.':
                        if popAfterwards:
                            self.readToken()
                            bytecodes.append(Bytecode.POP) # POP
                        break
                        # Push bytecode to pop one off the stack
        
        while self.peekToken() != b']':
            bytecodeOneLine()

        if addReturn:
            bytecodes.append(Bytecode.PUSH_SELF)
            bytecodes.append(Bytecode.RETURN)


        return (bytecodes, literalPtrs)
    
    def readMethod(self, forClass):
        assert self.stream.read(1) == b'['
        self.consumeComment()
        newMethod = QSILMethod()
        newMethod.objId = self.nextObjectId()
        tok = self.readToken()
        visibility = []
        while tok in [b'public', b'private', b'protected', b'static']:
            visibility.append(tok)
            tok = self.readToken()
        newMethod.visibility = visibility

        funcName = tok
        args = []
        if (funcName.endswith(b':') or
            funcName in specials):
            args.append(self.readToken())
        if not funcName in specials:
            while self.peekToken().endswith(b':'):
                funcName += self.readToken()
                args.append(self.readToken())
        newMethod.name = funcName
        newMethod.args = args
        
        # Implement actual method parsing and bytecodes later
        self.skipwhitespace()
        specialBytecodes = []
        if self.peek() == b'<':
            # Something special, it's telling us which bytecodes
            assert self.readToken() == b'<bytecodes'
            bytecodes = [bytes([int(bc, 16)]) for bc in self.readString().split(b' ')]
            specialBytecodes = bytecodes
            self.skipwhitespace()
            assert self.stream.read(1) == b'>'
        
        bytecodes, literalPtrs = self.methodToBytecodes(args)

        newMethod.bytecodes = specialBytecodes + bytecodes
        newMethod.literalPtrs = literalPtrs
        newMethod._class = forClass

        while self.peekToken() != b']': # Maybe it's part of the method, no whitespace. FIXME
            self.readToken()
        self.skipwhitespace()
        assert self.stream.read(1) == b']'
        self.consumeComment()

        return newMethod

    def readMethods(self, forClass):
        self.skipwhitespace()
        assert self.stream.read(2) == b'#('
        self.consumeComment()
        self.skipwhitespace()
        methods = []
        while self.peek() == b'[':
            methods.append(self.readMethod(forClass))
            self.skipwhitespace()
        assert self.stream.read(1) == b')'
        return methods

    def readclass(self):
        self.skipwhitespace()
        assert self.stream.read(1) == b'['
        self.consumeComment()
        newClass = QSILClass()
        newClass.superclass = self.readToken()
        newClass.type = self.readToken()
        newClass.name = self.readToken()[1:]
        if newClass.name == b'Object':
            newClass.classId = SpecialIDs.OBJECT_CLASS_ID
        elif newClass.name == b'ByteString':
            newClass.classId = SpecialIDs.BYTESTRING_CLASS_ID
        elif newClass.name == b'Character':
            newClass.classId = SpecialIDs.CHARACTER_CLASS_ID
        elif newClass.name == b'Integer':
            newClass.classId = SpecialIDs.INTEGER_CLASS_ID
        elif newClass.name == b'Class':
            newClass.classId = SpecialIDs.CLASS_CLASS_ID
        elif newClass.name == b'Method':
            newClass.classId = SpecialIDs.METHOD_CLASS_ID
        elif newClass.name == b'MethodContext':
            newClass.classId = SpecialIDs.METHODCONTEXT_CLASS_ID
        elif newClass.name == b'BlockContext':
            newClass.classId = SpecialIDs.BLOCKCONTEXT_CLASS_ID
        elif newClass.name == b'Float':
            newClass.classId = SpecialIDs.FLOAT_CLASS_ID
        elif newClass.name == b'Symbol':
            newClass.classId = SpecialIDs.SYMBOL_CLASS_ID
        elif newClass.name == b'OrderedCollection':
            newClass.classId = SpecialIDs.ORDEREDCOLLECTION_CLASS_ID
        elif newClass.name == b'True':
            newClass.classId = SpecialIDs.TRUE_CLASS_ID
        elif newClass.name == b'False':
            newClass.classId = SpecialIDs.FALSE_CLASS_ID
        elif newClass.name == b'UndefinedObject':
            newClass.classId = SpecialIDs.UNDEFINEDOBJECT_CLASS_ID
        elif newClass.name == b'QSILImage':
            newClass.classId = SpecialIDs.QSILIMAGE_CLASS_ID
        else:
            newClass.classId = self.nextObjectId()
        assert self.readToken() == b'instanceVariableNames:'
        newClass.instancevariables = [x for x in self.readString().split(b' ') if x]
        assert self.readToken() == b'classVariableNames:'
        newClass.classvariables = [x for x in self.readString().split(b' ') if x]
        assert self.readToken() == b'methods:'
        newClass.methods = self.readMethods(newClass.classId)
        if newClass.name == b'Bootstrap':
            global bootstrapPtr
            bootstrapPtr = Pointer.forObject(newClass.methods[0])
        self.skipwhitespace()
        assert self.stream.read(1) == b']'
        return newClass
    
    def doLateBinds(self):
        # Fix all sorts of references and stuff
        classInstVars = {}
        classClassVars = {}
        classNames = {}
        for eachClass in self.classes.values():
            instVars = []
            classVars = []
            classNames[eachClass.name] = eachClass
            if eachClass.superclass in classInstVars:
                instVars.extend(classInstVars[eachClass.superclass])
                classVars.extend(classClassVars[eachClass.superclass])
            instVars.extend(eachClass.instancevariables)
            classVars.extend(eachClass.classvariables)
            classInstVars[eachClass.name] = instVars
            classClassVars[eachClass.name] = classVars
        #print(classInstVars)
        #print(classClassVars)

        #print(classNames)
        def fixBytecodes(originalbytecodes):
            newbytecodes = []
            for bc in originalbytecodes:
                if isinstance(bc, list):
                    if bc[0] == 'latebindliteral':
                        search = bc[1]
                        if search in instVars:
                            newbytecodes.append(Bytecode.PUSH_INSTVAR)
                            newbytecodes.append(bytes([instVars.index(search)]))
                        elif search in classNames:
                            newbytecodes.append(Bytecode.PUSH_OBJ_REF)
                            newbytecodes.append(pack("<i", classNames[search].classId))
                        else:
                            print(f"Unknown {bc}")
                    elif bc[0] == 'latebindlvalue':
                        search = bc[1]
                        if search in instVars:
                            newbytecodes.append(Bytecode.POP_INTO_INSTVAR)
                            newbytecodes.append(bytes([instVars.index(search)]))
                        else:
                            print(f"Unknown {bc}")
                    else:
                        print(f"UNKNOWN {bc}")
                else:
                    newbytecodes.append(bc)
            return newbytecodes
        
        # Needs a second pass after getting the names of each
        # instance variable, class variable, and existing classes
        for eachClass in self.classes.values():
            instVars = classInstVars[eachClass.name]
            classVars = classClassVars[eachClass.name]
            for method in eachClass.methods:
                method.bytecodes = fixBytecodes(method.bytecodes)
        
        for bc in self.blockContexts:
            bytecodeObject = self.objects[bc.pyObjStorage[-2].objId]
            fixedBc = b''
            for bc in fixBytecodes(bytecodeObject.pyObjStorage):
                if isinstance(bc, bytes):
                    fixedBc += bc
                else:
                    fixedBc += bytes([bc])
            bytecodeObject.pyObjStorage = fixedBc

    def readall(self):
        self.skipwhitespace()
        while self.peek() == b'"':
            self.consumeComment()
            self.skipwhitespace()
        self.skipwhitespace()
        assert self.peek() == b'['

        while (self.peek()):
            self.consumeComment()
            self.skipwhitespace()
            eachClass = self.readclass()
            self.classes[eachClass.name] = eachClass

        self.doLateBinds()

        if printBytecodes:
            for eachClass in self.classes.values():
                if eachClass.methods:
                    clsId = pack("<i", eachClass.classId)
                    print(f"***CLASS {clsId} {eachClass.name}***")
                    for method in eachClass.methods:
                        print(f"\t***FUNCTION #{method.name} ***")
                        print(f"\t\t**BYTECODES**")
                        for bc in method.bytecodes:
                            print('\t\t{}'.format(bc))
                        print("\n\t\t**LITERALS**")
                        for lit in method.literalPtrs:
                            print('\t\t{}'.format(self.objects[lit.objId]))
                        #pprint.pprint([funcName, bytecodes, [self.objects[x.objId] for x in literalPtrs]])
                        print(f"\n\t***END FUNCTION #{method.name} ***")
                    print(f"***END CLASS {eachClass.name}***")
                else:
                    print(f"***EMPTY CLASS {eachClass.name}***")

            for context in self.blockContexts:
                print("***BLOCKCONTEXT***")
                print("\t**BYTECODES**")
                for bc in self.objects[context.pyObjStorage[0].objId].pyObjStorage:
                    print('\t{}'.format(bc))
                print("\n\t**LITERALS**")
                for lit in self.objects[context.pyObjStorage[1].objId].pyObjStorage:
                    print('\t{}'.format(self.objects[lit.objId]))
                #pprint.pprint([funcName, bytecodes, [self.objects[x.objId] for x in literalPtrs]])
                print("\n***END BLOCKCONTEXT***")

        # Now that all the bytecodes are complete, serialize all the classes into the proper QSIL format
        for eachClass in self.classes.values():
            eachClass.asQSILObject(self)

        # And finally, make sure to create some of the
        # singleton objects (nil, true, false, etc.)
        nil = Object()
        nil.objId = SpecialIDs.NIL_OBJECT_ID
        nil.classId = SpecialIDs.UNDEFINEDOBJECT_CLASS_ID
        self.objects[nil.objId] = nil

        trueObj = Object()
        trueObj.objId = SpecialIDs.TRUE_OBJECT_ID
        trueObj.classId = SpecialIDs.TRUE_CLASS_ID
        self.objects[trueObj.objId] = trueObj

        falseObj = Object()
        falseObj.objId = SpecialIDs.FALSE_OBJECT_ID
        falseObj.classId = SpecialIDs.FALSE_CLASS_ID
        self.objects[falseObj.objId] = falseObj

        # Also need QSILImage object, but that'll be a bit later
        qsilImage = Object()
        qsilImage.objId = SpecialIDs.QSIL_IMAGE_ID
        qsilImage.classId = SpecialIDs.QSILIMAGE_CLASS_ID
        self.objects[qsilImage.objId] = qsilImage

        allClassesPtr = self.qsilOrderedCollectionPtr(list([Pointer.forObject(x) for x in self.objects.values()]))

        qsilImage.setMem([allClassesPtr])

        # Now we need to create a MethodContext pointing to the
        # beginning of the Bootstrap>bootstrap method
        bootstrapCtx = Object()
        bootstrapCtx.objId = self.nextObjectId()
        bootstrapCtx.classId = SpecialIDs.METHODCONTEXT_CLASS_ID

        pcPtr = self.qsilNumberPtr(0)
        stackPtr = self.qsilOrderedCollectionPtr([])
        receiverPtr = Pointer()
        receiverPtr.objId = SpecialIDs.NIL_OBJECT_ID
        tempvarsPtr = self.qsilOrderedCollectionPtr([])
        parentContextPtr = Pointer()
        parentContextPtr.objId = SpecialIDs.NIL_OBJECT_ID
        argsPtr = self.qsilOrderedCollectionPtr([])

        bootstrapCtx.setMem([pcPtr, stackPtr, receiverPtr, tempvarsPtr, parentContextPtr, argsPtr, bootstrapPtr])
        self.objects[bootstrapCtx.objId] = bootstrapCtx

        outputBytes = b''
        outputBytes += pack("<i", len(self.objects))
        for obj in sorted(self.objects.values(), key=(lambda x: x.objId)):
            print(obj)
            outputBytes += obj.bytesForSerialization()

        outputBytes += pack("<i", bootstrapCtx.objId)

        print("Serialized {} objects".format(len(self.objects)))

        return outputBytes

if __name__ == '__main__':
    print("QSIL Bootstrapper")
    p = Parser(open("qsil1.sources", "rb"))
    out = p.readall()
    with open("qsil1.image", "wb") as outFile:
        outFile.write(out)
    print("Wrote {} bytes".format(len(out)))