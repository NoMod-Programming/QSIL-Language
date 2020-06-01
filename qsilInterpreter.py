#!/usr/bin/env python3
# Quick Self-Interpreting Language (QSIL)
# By Hazel P., 2020. Licensed under the MIT License

import ctypes
import struct

imageFormat = 1 # The image format version we're using

QSIL_TYPE_POINTER = 0 # Pointer to an object
QSIL_TYPE_POINTEROBJECT = 1 # Regular object with instance variables, all of which are pointers
QSIL_TYPE_DIRECTOBJECT = 2 # Object whose directmemory is used to store a value directly
QSIL_TYPE_DIRECTPOINTEROBJECT = 3 # Regular object with indexed variables, all of which are pointers
QSIL_TYPE_SUPERPOINTER = 4 # Any type with this or higher triggers special behavior when searching methods
                           # 4 - object id 0 as the superclass id, 5 - object id 1 as the superclass id, etc.

class Bytecode(object):
    PUSH_SELF  = 0 # Implemented
    PUSH_SUPER = 1 # Not implemented
    PUSH_NIL   = 2 # Implemented
    PUSH_TRUE  = 3 # Implemented
    PUSH_FALSE = 4 # Implemented

    PUSH_LITERAL = 5 # Implemented
    PUSH_ARG = 6 # Implemented
    PUSH_TEMP = 7 # Implemented
    PUSH_INSTVAR = 8 # Implemented

    RETURN = 9 # Implemented

    POP = 10 # Implemented
    POP_INTO_TEMP = 11 # Implemented
    POP_INTO_INSTVAR = 12 # Implemented

    PUSH_OBJ_REF = 13 # Implemented

    CALL = 14 # Implemented

    JUMP = 15 # Implemented
    JUMP_IF_TRUE = 16 # Implemented

    BECOME_ACTIVECONTEXT = 17 # Implemented

    ALLOC_NEW = 18 # Implemented
    ALLOC_NEW_WITHSIZE = 19 # Implemented

    # 1,2, skip a few, primitives for math stuff
    PRIM_ADD = 64 # Implemented

specials = [b'+', b',' b'-', b'/', b'*', b'>',
            b'<', b'<=',b'>=', b'=', b'~=', b'==',
            b'~==', b'&&', b'||', b'\\']

class VisibilityTypes(object):
    # Bit 1 - Prevents subclasses from accessing
    # Bit 2 - Prevents non-subclasses from accessing
    # Bit 3 - Is static?
    PRIVATE   = 0b110
    PROTECTED = 0b010
    STATIC    = 0b001

class SpecialIDs(object):
    OBJECT_CLASS_ID = 0
    BYTESTRING_CLASS_ID = 1
    TRUE_OBJECT_ID = 2
    FALSE_OBJECT_ID = 3
    NIL_OBJECT_ID = 4
    CHARACTER_CLASS_ID = 5
    ORDEREDCOLLECTION_CLASS_ID = 6
    SYMBOL_CLASS_ID = 7
    INTEGER_CLASS_ID = 8
    QSIL_IMAGE_ID = 9 # Like the global Smalltalk object
    CLASS_CLASS_ID = 10
    METHOD_CLASS_ID = 11
    METHODCONTEXT_CLASS_ID = 12
    BLOCKCONTEXT_CLASS_ID = 13
    FLOAT_CLASS_ID = 14
    TRUE_CLASS_ID = 15
    FALSE_CLASS_ID = 16
    UNDEFINEDOBJECT_CLASS_ID = 17
    QSILIMAGE_CLASS_ID = 18

    numObjs = 19

class QSILObject(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ('type', ctypes.c_uint8),
        ('objId', ctypes.c_uint32)
    ]
    def __init__(self, *args, **kwargs):
        super(QSILObject, self).__init__(*args, **kwargs)
        self.interp = None
        self._cachedself = None

    @property
    def u(self):
        if self._cachedself is None:
            self._cachedself = self.interp.objects[self.objId]
        return self._cachedself

    @property
    def ptr(self):
        return Pointer.forObject(self)
    
    @property
    def _class(self):
        return self.u._class

    @property
    def _superclass(self):
        return self.u._superclass

class Pointer(QSILObject):
    _pack_ = 1
    _fields_ = [
    ]
    def __init__(self, *args, **kwargs):
        super(Pointer, self).__init__(*args, **kwargs)

        self.type = QSIL_TYPE_POINTER

    def __repr__(self):
        return f'[Pointer id {self.objId}]'

    def copy(self):
        ret = Pointer()
        ret.interp = self.interp
        ret.objId = self.objId
        return ret

    @classmethod
    def forObject(cls, qsilObj):
        ret = cls()
        ret.objId = qsilObj.objId
        return ret
    
    def bytesForSerialization(self):
        if True:
            raise RuntimeError("Shouldn't get here")
        output = b''
        output += struct.pack("<2i", self.type, self.objId)
        return output

class Object(QSILObject):
    _pack_ = 1
    _fields_ = [
        ('classId', ctypes.c_uint32)
    ]
    def __init__(self, *args, **kwargs):
        super(Object, self).__init__(*args, **kwargs)

        self.type = QSIL_TYPE_POINTEROBJECT
        # Need something resizable due to ctypes limitations
        self.pyObjStorage = []

    def setMem(self, memory):
        self.pyObjStorage = memory

    def __repr__(self):
        return f'[Object id {self.objId} classid {self.classId} storage {self.pyObjStorage}]'
    
    def bytesForSerialization(self):
        output = b''
        output += struct.pack("<4i", self.type, self.objId, self.classId, len(self.pyObjStorage))
        storageType = ''

        for item in self.pyObjStorage:
            if isinstance(item, Pointer):
                assert (storageType or 'pointer') == 'pointer'
                storageType = 'pointer'
                output += struct.pack("<i", item.objId)
            else:
                assert (storageType or 'direct') == 'direct'
                storageType = 'direct'
                if isinstance(item, int):
                    item = bytes([item])
                output += item
        return output
    
    @classmethod
    def readFrom(cls, stream, interp=None):
        ret = cls()
        ret.interp = interp
        ret.type, ret.objId, ret.classId, numObjs = struct.unpack("<4i", stream.read(16))
        if ret.type == QSIL_TYPE_DIRECTOBJECT:
            ret.setMem(stream.read(numObjs))
        elif ret.type in [QSIL_TYPE_POINTEROBJECT, QSIL_TYPE_DIRECTPOINTEROBJECT]:
            objs = []
            for _ in range(numObjs):
                ptr = Pointer()
                ptr.interp = interp
                ptr.objId = struct.unpack("<i", stream.read(4))[0]
                objs.append(ptr)
            ret.setMem(objs)
        else:
            print("unknown")
            raise RuntimeError("Here")
        return ret

    @property
    def _class(self):
        return self.interp.objects[self.classId]

    @property
    def _superclass(self):
        if self.classId == SpecialIDs.CLASS_CLASS_ID:
            return self.pyObjStorage[2].u
        else:
            return self._class._superclass

    @property
    def u(self):
        return self

class Interpreter(object):
    """
    The interpreter interprets the bytecodes that QSIL runs on.
    """
    def __init__(self):
        self.activeContext = None
        self.objects = {}
        self.activeObjects = []
        self.highestId = 0
        self.consolidationCounter = 10000

        # Cached for speed
        self.bytecodes = None
        self.pc = None
    
    def readFile(self, fileName):
        with open(fileName, "rb") as inputFile:
            numObjects = struct.unpack("<i", inputFile.read(4))[0]
            for _ in range(numObjects):
                newObj = Object.readFrom(inputFile, self)
                self.objects[newObj.objId] = newObj
                self.highestId = max((self.highestId, newObj.objId))
            
            contextObjId = struct.unpack("<i", inputFile.read(4))[0]
            self.setActiveContext(self.objects[contextObjId])
    
    def incrementPc(self):
        self.pc += 1
        return self.pc

    def nextObjectId(self):
        # O(log(n)) algorithm
        # ids = list(sorted(self.objects.keys()))
        # start = 0
        # end = len(ids) - 1
        # while(start <= end):
        #     mid = (start + end) // 2
        #     if ids[mid] > mid:
        #         result = mid - 1
        #         end = mid - 1
        #     else:
        #         start = mid + 1
        #         result = mid + 1
        # nextId = result
        self.highestId += 1
        self.objects[self.highestId] = None
        return self.highestId

    def setActiveContext(self, aContext):
        # Store the old PC on the current context
        if self.activeContext:
            pcPtr = self.activeContext.pyObjStorage[0].u
            pcBytes = struct.pack("<i", self.pc)
            pcPtr.pyObjStorage = pcBytes

        self.activeContext = aContext
        pcPtr = self.activeContext.pyObjStorage[0].u
        pcBytes = pcPtr.pyObjStorage
        self.pc = struct.unpack("<i", pcBytes)[0]

        contextType = self.activeContext.classId
        if contextType == SpecialIDs.METHODCONTEXT_CLASS_ID:
            method = self.activeContext.u.pyObjStorage[6].u
            assert method.classId == SpecialIDs.METHOD_CLASS_ID

            methodbytecodes = method.pyObjStorage[3].u
            self.bytecodes = methodbytecodes.pyObjStorage
        elif contextType == SpecialIDs.BLOCKCONTEXT_CLASS_ID:
            blockBytecodes = self.activeContext.u.pyObjStorage[7].u
            self.bytecodes = blockBytecodes.pyObjStorage
        else:
            self.prettyPrintObject(self.activeContext)
            raise RuntimeError("No bytecode available!")
    
    def setPc(self, newPc):
        self.pc = newPc

    def peekBc(self):
        if self.pc >= len(self.bytecodes):
                return -1
        return self.bytecodes[self.pc]

    def prettyPrintObject(self, anObj, doneObjects = None, indent=0):
        doneObjects = doneObjects or []
        ret = ''
        if anObj in doneObjects:
            ret += "|  " * (indent) + "Object ID {}".format(anObj.objId)
            return ret
        else:
            doneObjects.append(anObj)
        objClass = anObj._class
        ret += '|  ' * indent + "{} ".format(anObj.objId) + (objClass.pyObjStorage[1].u.pyObjStorage).decode("utf-8")
        if anObj.u.type == QSIL_TYPE_DIRECTOBJECT:
            ret += '\n'
            ret += "|  " * (indent + 1) + "{}".format(anObj.u.pyObjStorage)
        elif anObj.u.type == QSIL_TYPE_DIRECTPOINTEROBJECT:
            if anObj.u.pyObjStorage:
                for obj in anObj.u.pyObjStorage:
                    ret += '\n'
                    ret += self.prettyPrintObject(obj, doneObjects, indent + 1)
                
            else:
                ret += '\n' + '|  ' * (indent + 1) + 'Empty'
        else:
            for i, instVar in enumerate(objClass.pyObjStorage[3].u.pyObjStorage):
                ret += '\n'
                ret += "|  " * (indent + 1) + "Key, value:\n"
                ret += self.prettyPrintObject(instVar, [], indent + 2)
                ret += '\n'
                ret += self.prettyPrintObject(anObj.u.pyObjStorage[i], doneObjects, indent + 2)

        if indent == 0:
            print(ret)
        else:
            return ret

    def qsilNumberPtr(self, num):
        qsilNumber = Object()
        qsilNumber.interp = self
        qsilNumber.classId = SpecialIDs.INTEGER_CLASS_ID if isinstance(num, int) else SpecialIDs.FLOAT_CLASS_ID
        qsilNumber.type = QSIL_TYPE_DIRECTOBJECT
        numToBytes = struct.pack("<i", num)
        qsilNumber.setMem(numToBytes)
        qsilNumber.objId = self.nextObjectId()
        self.objects[qsilNumber.objId] = qsilNumber

        ptr = Pointer.forObject(qsilNumber)
        ptr.interp = self
        return ptr

    def qsilOrderedCollectionPtr(self, objects):
        qsilOrderedCollection = Object()
        qsilOrderedCollection.interp = self
        qsilOrderedCollection.classId = SpecialIDs.ORDEREDCOLLECTION_CLASS_ID
        qsilOrderedCollection.type = QSIL_TYPE_DIRECTPOINTEROBJECT
        qsilOrderedCollection.setMem(objects)
        qsilOrderedCollection.objId = self.nextObjectId()
        self.objects[qsilOrderedCollection.objId] = qsilOrderedCollection

        ptr = Pointer.forObject(qsilOrderedCollection)
        ptr.interp = self
        return ptr

    def pushToStack(self, item):
        contextType = self.activeContext.classId
        if contextType == SpecialIDs.METHODCONTEXT_CLASS_ID:
            stack = self.activeContext.u.pyObjStorage[1].u
            
            objPtr = Pointer.forObject(item)
            objPtr.interp = self

            stack.pyObjStorage.append(objPtr)
            return
        elif contextType == SpecialIDs.BLOCKCONTEXT_CLASS_ID:
            #print("Pushing to blockcontext stack!")
            stack = self.activeContext.u.pyObjStorage[1].u

            objPtr = Pointer.forObject(item)
            objPtr.interp = self

            stack.pyObjStorage.append(objPtr)
            return
        self.prettyPrintObject(self.activeContext)
        raise RuntimeError("No stack available!")

    def popFromStack(self, doPop=True):
        contextType = self.activeContext.classId
        if contextType == SpecialIDs.METHODCONTEXT_CLASS_ID:
            stack = self.activeContext.u.pyObjStorage[1].u
            if doPop:
                return stack.pyObjStorage.pop()
            else:
                return stack.pyObjStorage[-1]
        elif contextType == SpecialIDs.BLOCKCONTEXT_CLASS_ID:
            #print("Popping from blockcontext stack!")
            stack = self.activeContext.u.pyObjStorage[1].u
            if doPop:
                return stack.pyObjStorage.pop()
            else:
                return stack.pyObjStorage[-1]
        self.prettyPrintObject(self.activeContext)
        raise RuntimeError("No stack available!")

    def getLiteral(self, index):
        contextType = self.activeContext.classId
        if contextType == SpecialIDs.METHODCONTEXT_CLASS_ID:
            #print("Getting literal for MethodContext!")
            method = self.activeContext.u.pyObjStorage[6].u
            assert method.classId == SpecialIDs.METHOD_CLASS_ID

            literals = method.pyObjStorage[4].u

            literal = literals.pyObjStorage[index]
            if literal.u.classId == SpecialIDs.BLOCKCONTEXT_CLASS_ID:
                # Need to do something here
                newBlock = self.blockCopy(literal)
                self.blockBind(newBlock)
                literal = Pointer.forObject(newBlock)
                literal.interp = self
                #print("We've popped a blockcontext")
            return literal
        elif contextType == SpecialIDs.BLOCKCONTEXT_CLASS_ID:
            #print("Getting literal from BlockContext!")
            literals = self.activeContext.u.pyObjStorage[6].u
            #self.prettyPrintObject(literals)
            return literals.pyObjStorage[index]
        self.prettyPrintObject(self.activeContext)
        raise RuntimeError("No literal available!")

    def getArg(self, index):
        args = self.activeContext.u.pyObjStorage[5].u
        return args.pyObjStorage[index]

    def contextForStack(self):

        # Get the selector's name and figure out how many arguments
        # it takes
        selector = self.popFromStack().u
        assert selector.classId == SpecialIDs.SYMBOL_CLASS_ID
        selectorName = selector.pyObjStorage

        numArgs = 0
        if selectorName in specials:
            numArgs = 1
        else:
            numArgs = selectorName.count(b':')
        
        # Push the necessary number of arguments onto the stack
        args = []
        while len(args) < numArgs:
            args.insert(0, self.popFromStack())
        
        # Get the receiver and search it's class (or superclass)
        # for the method
        rcvr = self.popFromStack().u
        foundMethod = None
        searchedObjectClass = False
        
        # If the receiver is a class, then look for static
        # methods, not public/private ones
        searchFlags = []
        
        currClass = rcvr._class.u
        if rcvr.classId == SpecialIDs.CLASS_CLASS_ID:
            searchFlags.append(VisibilityTypes.STATIC)
        else:
            if rcvr.classId == self.activeContext.u.pyObjStorage[2].u.classId:
                searchFlags.extend([VisibilityTypes.PROTECTED | VisibilityTypes.PRIVATE])

        def matchesSearchFlags(visibility):
            if VisibilityTypes.STATIC in searchFlags:
                return not (visibility ^ VisibilityTypes.STATIC)
            else:
                return True

        while not searchedObjectClass and not foundMethod:
            assert currClass.classId == SpecialIDs.CLASS_CLASS_ID
            methods = currClass.pyObjStorage[5].u
            for method in methods.pyObjStorage:
                methodName = method.u.pyObjStorage[0].u
                visibilityPtr = method.u.pyObjStorage[1].u
                visibility = struct.unpack("<i", visibilityPtr.pyObjStorage)[0]
                if methodName.pyObjStorage == selectorName:
                    if matchesSearchFlags(visibility):
                        foundMethod = method
                        break
            if currClass.objId == SpecialIDs.OBJECT_CLASS_ID:
                searchedObjectClass = True
            if currClass.objId == SpecialIDs.CLASS_CLASS_ID:
                currClass = rcvr
            else:
                currClass = currClass.pyObjStorage[2].u
        
        if foundMethod is None:
            # Call #doesNotUnderstand:
            #self.prettyPrintObject(self.activeContext)
            raise RuntimeError("No method found for {}!".format(selectorName))

        #self.prettyPrintObject(foundMethod)
        #print("Called method")

        newCtx = Object()
        newCtx.interp = self
        newCtx.objId = self.nextObjectId()
        newCtx.classId = SpecialIDs.METHODCONTEXT_CLASS_ID

        pcPtr = self.qsilNumberPtr(0)
        stackPtr = self.qsilOrderedCollectionPtr([])
        receiverPtr = Pointer.forObject(rcvr)
        receiverPtr.interp = self
        tempvarsPtr = self.qsilOrderedCollectionPtr([])
        parentContextPtr = Pointer.forObject(self.activeContext)
        parentContextPtr.interp = self
        argsPtr = self.qsilOrderedCollectionPtr(args)
        argsPtr.interp = self

        newCtx.setMem([pcPtr, stackPtr, receiverPtr, tempvarsPtr, parentContextPtr, argsPtr, foundMethod])

        self.objects[newCtx.objId] = newCtx

        return newCtx

    def qsilStringPtr(self, string):
        qsilString = Object()
        qsilString.classId = SpecialIDs.BYTESTRING_CLASS_ID
        qsilString.type = QSIL_TYPE_DIRECTOBJECT
        qsilString.setMem(string)
        qsilString.objId = self.nextObjectId()
        self.objects[qsilString.objId] = qsilString

        ptr = Pointer.forObject(qsilString)
        ptr.interp = self
        return ptr

    def blockCopy(self, blockCtx):
        # May need to redo literal pushing so that
        # popping a block also sets its receiver and
        # args
        # NONE OF THIS CODE WORKS YET, REDO

        #self.prettyPrintObject(interp.activeContext)
        #self.prettyPrintObject(blockCtx)

        method = self.activeContext.u.pyObjStorage[6].u
        assert method.classId == SpecialIDs.METHOD_CLASS_ID

        
        qsilBlockContext = Object()
        qsilBlockContext.classId = SpecialIDs.BLOCKCONTEXT_CLASS_ID
        qsilBlockContext.interp = self

        pcPtr = self.qsilNumberPtr(0)
        pcPtr.interp = self
        stackPtr = self.qsilOrderedCollectionPtr([])
        stackPtr.interp = self
        receiverPtr = Pointer.forObject(self.activeContext.u.pyObjStorage[2])
        receiverPtr.interp = self
        tempvarsPtr = self.activeContext.u.pyObjStorage[3] # TODO: See if this actually works properly
        tempvarsPtr.interp = self
        argsPtr = self.activeContext.u.pyObjStorage[5]
        argsPtr.interp = self
        parentContextPtr = Pointer()
        parentContextPtr.objId = SpecialIDs.NIL_OBJECT_ID
        parentContextPtr.interp = self
        bytecodesPtr = blockCtx.u.pyObjStorage[7]
        literalsPtr = blockCtx.u.pyObjStorage[6]
        homePtr = Pointer.forObject(self.activeContext)
        homePtr.interp = self

        bcMem = [pcPtr, stackPtr, receiverPtr, tempvarsPtr, parentContextPtr, argsPtr, literalsPtr, bytecodesPtr, homePtr]
        qsilBlockContext.setMem(bcMem)
        qsilBlockContext.objId = self.nextObjectId()
        self.objects[qsilBlockContext.objId] = qsilBlockContext

        ptr = Pointer.forObject(qsilBlockContext)
        ptr.interp = self

        #self.prettyPrintObject(ptr)

        return ptr
    
    def getTemp(self, tempNumber):
        tempVarsPtr = self.activeContext.u.pyObjStorage[3]
        if len(tempVarsPtr.u.pyObjStorage) <= tempNumber:
            nullPtr = Pointer()
            nullPtr.interp = self
            nullPtr.objId = SpecialIDs.NIL_OBJECT_ID
            return nullPtr
        return tempVarsPtr.u.pyObjStorage[tempNumber]

    def setTemp(self, tempNumber, tempValue):
        tempVarsPtr = self.activeContext.u.pyObjStorage[3]
        if len(tempVarsPtr.u.pyObjStorage) <= tempNumber:
            diff = (tempNumber - len(tempVarsPtr.u.pyObjStorage)) + 1
            nullPtr = Pointer()
            nullPtr.interp = self
            nullPtr.objId = SpecialIDs.NIL_OBJECT_ID
            tempVarsPtr.u.pyObjStorage.extend(nullPtr.copy() for _ in range(diff))
        tempVarsPtr.u.pyObjStorage[tempNumber] = tempValue

    def getInstvar(self, varNumber):
        rcvr = self.activeContext.u.pyObjStorage[2]
        return rcvr.u.pyObjStorage[varNumber]

    def setInstvar(self, varNumber, varValue):
        rcvr = self.activeContext.u.pyObjStorage[2]
        rcvr.u.pyObjStorage[varNumber] = varValue

    def blockBind(self, blockCtx):
        #self.prettyPrintObject(blockCtx)
        pass

    def interpretOne(self, printBytecode = False):
        bc = self.peekBc()
        if printBytecode:
            print(bc, self.pc)
        # PUSH GLOBAL CONSTANTS
        #print(self.consolidationCounter)
        self.consolidationCounter -= 1
        if self.consolidationCounter == 0:
            self.garbageCollect()

        if bc == -1:
            #print("BlockContext ended, returning to parent context")
            parentContext = self.activeContext.u.pyObjStorage[4]
            ret = self.popFromStack()
            self.setActiveContext(parentContext.u)
            self.pushToStack(ret)
            return
        elif bc == Bytecode.PUSH_SELF:
            #print("Push self")
            self.incrementPc()
            rcvr = self.activeContext.u.pyObjStorage[2]
            self.pushToStack(rcvr)
            return
        elif bc == Bytecode.PUSH_SUPER:
            #print("Push super")
            # TODO: Continue implementing this
            self.incrementPc()
            rcvr = self.activeContext.u.pyObjStorage[2]
            foundMethod = self.activeContext.u.pyObjStorage[6]
            methodClass = foundMethod.u.pyObjStorage[5].u
            superPtr = Pointer()
            superPtr.interp = self
            superPtr.objId = QSIL_TYPE_SUPERPOINTER + methodClass.objId
            self.pushToStack(superPtr)
            return
        elif bc == Bytecode.PUSH_NIL:
            #print("Push nil")
            self.incrementPc()
            truePtr = Pointer()
            truePtr.interp = self
            truePtr.objId = SpecialIDs.NIL_OBJECT_ID
            self.pushToStack(truePtr)
            return
        elif bc == Bytecode.PUSH_TRUE:
            #print("Push true")
            self.incrementPc()
            truePtr = Pointer()
            truePtr.interp = self
            truePtr.objId = SpecialIDs.TRUE_OBJECT_ID
            self.pushToStack(truePtr)
            return
        elif bc == Bytecode.PUSH_FALSE:
            #print("Push false")
            self.incrementPc()
            truePtr = Pointer()
            truePtr.interp = self
            truePtr.objId = SpecialIDs.FALSE_OBJECT_ID
            self.pushToStack(truePtr)
            return
        # PUSH OTHER
        elif bc == Bytecode.PUSH_LITERAL:
            #print("Push literal")
            self.incrementPc()
            literalIndex = self.peekBc()
            lit = self.getLiteral(literalIndex)
            #self.prettyPrintObject(lit)
            self.pushToStack(lit)
            self.incrementPc()
            return
        elif bc == Bytecode.PUSH_ARG:
            #print("Push arg")
            self.incrementPc()
            argIndex = self.peekBc()
            arg = self.getArg(argIndex)
            #self.prettyPrintObject(arg)
            self.pushToStack(arg)
            self.incrementPc()
            return
        elif bc == Bytecode.PUSH_TEMP:
            #print("Push temp")
            self.incrementPc()
            tempNumber = self.peekBc()
            val = self.getTemp(tempNumber)
            self.incrementPc()
            self.pushToStack(val)
            return
        elif bc == Bytecode.PUSH_INSTVAR:
            #print("Push instvar")
            self.incrementPc()
            varNumber = self.peekBc()
            val = self.getInstvar(varNumber)
            self.incrementPc()
            self.pushToStack(val)
            return
        elif bc == Bytecode.RETURN:
            #print("Returning!")
            if self.activeContext.u.classId == SpecialIDs.BLOCKCONTEXT_CLASS_ID:
                homeContext = self.activeContext.u.pyObjStorage[8]
                ret = self.popFromStack()
                interp.prettyPrintObject(ret)
                self.setActiveContext(homeContext.u)
                self.pushToStack(ret)
                return
            elif self.activeContext.u.classId == SpecialIDs.METHODCONTEXT_CLASS_ID:
                parentContext = self.activeContext.u.pyObjStorage[4]
                ret = self.popFromStack()
                self.setActiveContext(parentContext.u)
                self.pushToStack(ret)
                return
            self.prettyPrintObject(self.activeContext)
            raise RuntimeError("1.) Move this to its own method, and 2.) no parent?")
        # Popping
        elif bc == Bytecode.POP:
            #print("Popping from stack")
            self.popFromStack()
            self.incrementPc()
            return
        elif bc == Bytecode.POP_INTO_TEMP:
            #print("Pop into temp")
            valuePtr = self.popFromStack(False)
            self.incrementPc()
            tempNumber = self.peekBc()
            self.setTemp(tempNumber, valuePtr)
            self.incrementPc()
            return
        elif bc == Bytecode.POP_INTO_INSTVAR:
            #print("Pop into inst var")
            valuePtr = self.popFromStack(False)
            self.incrementPc()
            varNumber = self.peekBc()
            self.setInstvar(varNumber, valuePtr)
            self.incrementPc()
            return
        # Pushing class references (TODO: Check if this even needed)
        # Could just push literal since it'd act the same. Everything's
        # first-class
        # Could just turn this into the <new> bytecode
        elif bc == Bytecode.PUSH_OBJ_REF:
            self.incrementPc()
            ptr = Pointer()
            ptr.interp = self
            objId = 0
            for i in range(4):
                objId += self.peekBc() << (i*8)
                self.incrementPc()
            ptr.objId = objId
            self.pushToStack(ptr)
            return
        elif bc == Bytecode.CALL:
            self.incrementPc()
            newContext = self.contextForStack()
            self.setActiveContext(newContext)
            return
        elif bc == Bytecode.JUMP:
            #print("Unconditional jump")
            self.incrementPc()
            newPc = 0
            for i in range(4):
                newPc += self.peekBc() << (i*8)
                self.incrementPc()
            self.setPc(newPc)
            return
        elif bc == Bytecode.JUMP_IF_TRUE:
            #print("Conditional jump")
            self.incrementPc()
            newPc = 0
            for i in range(4):
                newPc += self.peekBc() << (i*8)
                self.incrementPc()
            arg = self.popFromStack()
            if arg.objId == SpecialIDs.TRUE_OBJECT_ID:
                self.setPc(newPc)
            return
        elif bc == Bytecode.BECOME_ACTIVECONTEXT:
            # TODO: Figure out if nexted blocks, e.g. [[^ self] value] value, would return or not
            self.incrementPc()
            rcvr = self.activeContext.u.pyObjStorage[2]
            self.blockBind(rcvr) # TODO: Implement

            parentContext = Pointer.forObject(self.activeContext)
            parentContext.interp = self

            rcvr.u.pyObjStorage[4] = parentContext
            self.setActiveContext(rcvr.u)
            self.setPc(0) # Jump to the beginning
            #print("Changed to a blockContext!")
            return
        elif bc == Bytecode.ALLOC_NEW:
            #print("Make a new object!")
            rcvr = self.activeContext.u.pyObjStorage[2].u
            assert rcvr.classId == SpecialIDs.CLASS_CLASS_ID

            newObj = Object()
            newObj.interp = self
            newObj.classId = rcvr.objId

            nullPtr = Pointer()
            nullPtr.interp = self
            nullPtr.objId = SpecialIDs.NIL_OBJECT_ID

            objType = rcvr.pyObjStorage[0].u.pyObjStorage
            if objType == b'subclass:':
                newObj.type = QSIL_TYPE_POINTEROBJECT
            else:
                raise RuntimeError("Unknown object type: {}".format(objType))

            numInstVars = len(rcvr.pyObjStorage[3].u.pyObjStorage)

            newObj.setMem([nullPtr.copy() for _ in range(numInstVars)])

            newObj.objId = self.nextObjectId()
            self.objects[newObj.objId] = newObj

            retPtr = Pointer.forObject(newObj)
            retPtr.interp = self

            self.pushToStack(retPtr)
            self.incrementPc()
            return
        elif bc == Bytecode.ALLOC_NEW_WITHSIZE:
            #print("Make a new object with size!")
            rcvr = self.activeContext.u.pyObjStorage[2].u
            assert rcvr.classId == SpecialIDs.CLASS_CLASS_ID

            newObj = Object()
            newObj.interp = self
            newObj.classId = rcvr.objId

            nullPtr = Pointer()
            nullPtr.interp = self
            nullPtr.objId = SpecialIDs.NIL_OBJECT_ID

            objType = rcvr.pyObjStorage[0].u.pyObjStorage
            if objType == b'subclass:':
                newObj.type = QSIL_TYPE_POINTEROBJECT
            else:
                raise RuntimeError("Unknown object type: {}".format(objType))

            sizePtr = self.getArg(0)
            numInstVars = struct.unpack('<i', sizePtr.u.pyObjStorage)[0]

            newObj.setMem([nullPtr.copy() for _ in range(numInstVars)])

            newObj.objId = self.nextObjectId()
            self.objects[newObj.objId] = newObj

            retPtr = Pointer.forObject(newObj)
            retPtr.interp = self

            self.pushToStack(retPtr)
            self.incrementPc()
            return
        elif bc == Bytecode.PRIM_ADD:
            # TODO: Probably should cache numbers from -127 to 127
            rcvr = self.activeContext.u.pyObjStorage[2]
            addTo = self.popFromStack()
            res = 0
            res += struct.unpack("<i", rcvr.u.pyObjStorage)[0]
            res += struct.unpack("<i", addTo.u.pyObjStorage)[0]
            self.pushToStack(self.qsilNumberPtr(res))
            self.incrementPc()
            return
        elif bc == 0xff:
            #print("TEMPORARY BYTECODE FOR PRINTING: MOVE TO PRIMS")
            self.incrementPc()
            item = self.getArg(0).u
            #print(item.objId)
            #print(struct.unpack("<i",item.pyObjStorage)[0])
            self.prettyPrintObject(item)
            return
        print(hex(bc))
        self.incrementPc()
        #self.prettyPrintObject(self.activeContext)

    def garbageCollect(self):
        # Garbage collect and consolidate object IDs
        if False:
            # Garbage collection is broken, may need to redo the algorithm and make it work properly
            # Save all pointers and objects to a list, and just set their objIds?
            return
        self.consolidationCounter = 10000

        classIds = []
        self.idsReferencedBy(self.objects[SpecialIDs.QSIL_IMAGE_ID], classIds)
        self.idsReferencedBy(self.activeContext, classIds)

        for specialId in range(SpecialIDs.numObjs):
            if specialId not in classIds:
                classIds.append(specialId)

        classIds = list(sorted(classIds))

        # print(classIds)

        hashMap = {}
        for id in range(len(classIds)):
            if id in classIds:
                hashMap[id] = id
                del classIds[classIds.index(id)]
            else:
                hashMap[classIds[-1]] = id
                del classIds[-1]

        doneObjects = []

        #print(hashMap)
        #print(self.objects[7208], hashMap[7208])

        self.remapObjects(self.objects[SpecialIDs.QSIL_IMAGE_ID], doneObjects, hashMap)
        self.remapObjects(self.activeContext, doneObjects, hashMap)
        #self.prettyPrintObject(self.activeContext)

        for anObj in doneObjects:
            anObj.objId = hashMap[anObj.objId]
            if anObj.type == QSIL_TYPE_DIRECTPOINTEROBJECT:
                self.objects[anObj.objId] = anObj
            elif anObj.type == QSIL_TYPE_POINTEROBJECT:
                self.objects[anObj.objId] = anObj
            elif anObj.type == QSIL_TYPE_DIRECTOBJECT:
                self.objects[anObj.objId] = anObj

        #print(hashMap)

        newObjs = {}
        for id in hashMap.values():
            newObjs[id] = self.objects[id]
        self.objects = newObjs

        self.highestId = len(hashMap) - 1


    def remapObjects(self, anObj, doneObjects, hashMap):
        if anObj in doneObjects:
            return
        else:
            doneObjects.append(anObj)

        self.remapObjects(anObj.u, doneObjects, hashMap)

        if anObj.type == QSIL_TYPE_POINTER:
            pass
        elif anObj.type == QSIL_TYPE_DIRECTOBJECT:
            pass
        else:
            self.remapObjects(anObj._class, doneObjects, hashMap)
            for obj in anObj.pyObjStorage:
                self.remapObjects(obj, doneObjects, hashMap)

    def idsReferencedBy(self, anObj, doneObjects):
        if anObj.objId in doneObjects:
            return
        else:
            doneObjects.append(anObj.objId)

        self.idsReferencedBy(anObj._class, doneObjects)

        actualObj = anObj.u
        if actualObj.type == QSIL_TYPE_DIRECTOBJECT:
            return
        elif actualObj.type == QSIL_TYPE_DIRECTPOINTEROBJECT:
            for obj in actualObj.pyObjStorage:
                self.idsReferencedBy(obj, doneObjects)
        else:
            for obj in actualObj.pyObjStorage:
                self.idsReferencedBy(obj, doneObjects)


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        sys.argv.append(f'qsil{imageFormat}.image')
    interp = Interpreter()
    interp.readFile(sys.argv[1])
    interp.objects[14] = None
    import time
    startTime = time.time()
    # interp.prettyPrintObject(interp.activeContext)
    num = 10000000
    for _ in range(num):
        interp.interpretOne()
    for _ in range(1):
        interp.interpretOne(True)
    elapsed = time.time() - startTime
    print("{} second elapsed".format(elapsed))
    print("{} instructions per second".format(num / elapsed))
    print(interp.highestId)
    print(len(interp.objects))

    # while True:
    #     interp.interpretOne()