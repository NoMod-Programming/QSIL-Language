# Quick Self-Interpreting Language (QSIL)
# By Edward Pedemonte, 2017. Licensed under the MIT License
import time
import threading
import struct
from io import BytesIO


class QSILObject:
    """
    The superclass for QSIL objects. Used for type checking
    """


class Pointer(QSILObject, object):
    """
    A pointer of sorts to an Object. This has a .yourself
    property that returns the object it refers to
    """
    def __init__(self, anId):
        self.id = anId

    def __repr__(self):
        return "Pointer({})".format(self.id)

    @property
    def yourself(self):
        return allobjects[self.id]

    def appendToSet(self, aCollection):
        aCollection.add(self)

    def __hash__(self):
        return id(self)


class Object(QSILObject, dict):
    """
    An object exists in memory. It can either be used internally,
    such as a stack "frame", or exist as a live object in QSIL
    """
    def __init__(self, *args, **kwargs):
        super(Object, self).__init__(*args, **kwargs)
        self.id = 0
        self.directMemory = []

    def __hash__(self):
        return id(self)

    def setId(self, anId):
        self.id = anId

    def setMem(self, aList):
        self.directMemory = aList

    def __repr__(self):
        initialValue = 'Object({})'.format(super(Object, self).__repr__())
        if self.id != 0:
            initialValue += '.setId({})'.format(self.id)
        if self.directMemory:
            initialValue += '.setMem({})'.format(self.directMemory.__repr__())
        return initialValue

    @property
    def yourself(self):
        return self

    def appendToSet(self, aCollection):
        aCollection.add(self)
        for key, value in self.items():
            if isinstance(value, QSILObject):
                value.appendToSet(aCollection)
        for value in self.directMemory:
            if isinstance(value, QSILObject):
                value.appendToSet(aCollection)


def read(bytesToRead):
    """
    Read all the objects from the given bytes() object
    """
    def peek(length=1):
        pos = byteStream.tell()
        ret = byteStream.read(length)
        byteStream.seek(pos)
        return ret
    byteStream = BytesIO(bytesToRead)
    assert byteStream.read(4) == b'QSIL', "Unknown file format"
    assert int(byteStream.read(1)) <= 1, "VM too old"

    def readSomething():
        toRead = int(byteStream.read(1)[0])
        if toRead == 0x00:
            return readObject()
        elif toRead == 0x02:
            return readAssociation()
        # elif toRead == 0x03  # Reserved for value in association
        elif toRead == 0x04:
            return readInt()
        elif toRead == 0x05:
            return readFloat()
        elif toRead == 0x06:
            return readPointer()
        elif toRead == 0x07:
            return readString()
        raise ValueError("Unknown type:", toRead)

    def readFloat():
        return struct.unpack('>d', byteStream.read(8))[0]

    def readInt():
        return struct.unpack('>i', byteStream.read(4))[0]

    def readPointer():
        anId = byteStream.read(6)
        assert byteStream.read(1)[0] == 0x06
        return Pointer(anId)

    def readAssociation():
        """Read an association. Used internally"""
        key = readSomething()
        assert byteStream.read(1)[0] == 0x03
        value = readSomething()
        return (key, value)

    def readString():
        theCode = b''
        while byteStream.tell() < len(byteStream.getvalue()):
            # Until we reach an "END STRING" marker, keep reading
            nextChar = byteStream.read(1)
            if nextChar[0] == 0x07:
                break
            elif nextChar[0] == 0x08:
                nextChar = byteStream.read(1)
            theCode += nextChar
        return theCode

    def readObject():
        """Read an object"""
        currentObj = Object()
        objId = byteStream.read(6)
        currentObj.setId(objId)
        allobjects[objId] = currentObj
        toRead = None
        while (byteStream.tell() < len(byteStream.getvalue())):
            toRead = peek()[0]
            if toRead == 0x02:
                # Special handling for associations
                byteStream.read(1)
                assoc = readAssociation()
                currentObj[assoc[0]] = assoc[1]
            elif toRead == 0x01:
                break
            else:
                toAdd = readSomething()
                currentObj.directMemory.append(toAdd)
        byteStream.read(1)  # Pop end of object descriptor
        return currentObj

    def readObjectNoId():
        """Read an object"""
        currentObj = Object()
        toRead = None
        while (byteStream.tell() < len(byteStream.getvalue())):
            toRead = peek()[0]
            if toRead == 0x02:
                # Special handling for associations
                byteStream.read(1)
                assoc = readAssociation()
                currentObj[assoc[0]] = assoc[1]
            elif toRead == 0x01:
                break
            else:
                toAdd = readSomething()
                currentObj.directMemory.append(toAdd)
        byteStream.read(1)  # Pop end of object descriptor
        return currentObj

    def readStack():
        newContext = Object()
        if byteStream.read(2) == b'ST':
            # Read a new context. Otherwise, return a blank one
            newContext['pc'] = readInt()
            newContext['method'] = readPointer()
            newContext['receiver'] = readPointer()
            assert byteStream.read(1)[0] == 0x00
            newContext['args'] = readObjectNoId()
            assert byteStream.read(1)[0] == 0x00
            newContext['tempvars'] = readObjectNoId()
            assert byteStream.read(1)[0] == 0x00
            newContext['stack'] = readObjectNoId()
            newContext['homeContext'] = readStack()  # Nested contexts...
        return newContext

    while byteStream.tell() < len(byteStream.getvalue()) and peek()[0] == 0x00:
        byteStream.read(1)
        readObject()
    assert byteStream.read(3) == b'\xab\xcd\xef', "No entry context"
    interp.setContext(readStack())


def rehashObjects():
    """Create a new unique id for every object.
Make sure to update all pointers to each object."""
    global allobjects
    minId = newId = 0  # Id to start with
    hashMap = {}
    newAllObjects = {}
    uniqueobjects = set()

    def store_48bitInt(intToStore):
        """Return the bytes for storage of a 48-bit integer"""
        if intToStore < -140737488355328 or intToStore >= 140737488355328:
            raise ValueError("Outside 48-bit integer range")
        if intToStore < 0:
            finalInt = 281474976710656 + intToStore
        else:
            finalInt = intToStore

        def digitAt(theInt, toFind):
            if toFind > 6:
                return 0
            if theInt < 0:
                return (0 - theInt >> ((toFind - 1) * 8)) & 0xFF
            return theInt >> ((toFind - 1) * 8) & 0xFF

        return bytes([digitAt(intToStore, x) for x in range(6, 0, -1)])

    for oldid, theObject in allobjects.items():
        theObject.appendToSet(uniqueobjects)
    for theObject in uniqueobjects:
        if sum(c << (i * 8) for i, c in enumerate(theObject.id[::-1])) < minId:
            continue  # Do not change the ID for this object
        if theObject.id in hashMap:
            theObject.id = hashMap[theObject.id]
        else:
            hashMap[theObject.id] = store_48bitInt(newId)
            theObject.id = store_48bitInt(newId)
            newId += 1
        if isinstance(theObject, Object):
            newAllObjects[theObject.id] = theObject
    uniqueobjects = set()
    interp.saveToContext()
    thisContext = interp.activeContext
    while 'pc' in thisContext:
        thisContext.appendToSet(uniqueobjects)
        for anObject in thisContext.directMemory:
            if isinstance(anObject, QSILObject):
                anObject.appendToSet(uniqueobjects)
        thisContext = thisContext['homeContext']
    uniqueobjects = [x for x in uniqueobjects if not isinstance(x.id, int)]
    for theObject in uniqueobjects:
        if sum(c << (i * 8) for i, c in enumerate(theObject.id[::-1])) < minId:
            continue  # Do not change the ID for this object
        theObject.id = hashMap[theObject.id]
    interp.readFromContext()
    allobjects = newAllObjects


class Interpreter(object):
    """
    The interpreter interprets the bytecodes that QSIL runs on.
    """
    def __init__(self):
        self.pc = 0
        self._method = None
        self._receiver = None
        self.activeContext = None
        self.args = []
        self.tempvars = []
        self._stack = []

    def setContext(self, aContextObject):
        self.activeContext = aContextObject
        self.readFromContext()

    def popContext(self):
        """
        Return to the previous context.
        Make sure to set all the state variables
        """
        oldContext = self.activeContext
        self.activeContext = oldContext['homeContext']
        self.setContext(self.activeContext)

    def pushContext(self, aContextObject):
        """
Push a new context object.
        Make sure that that context's parent is set to the
        current context and store all state variables
        """
        oldContext = self.activeContext
        aContextObject['homeContext'] = oldContext
        self.saveToContext()
        self.setContext(aContextObject)

    def saveToContext(self):
        # Save all the state variables to the context.
        # Method and receiver don't change in context
        self.activeContext['pc'] = self.pc
        self.activeContext['args'] = self.args
        self.activeContext['tempvars'] = self.tempvars
        self.activeContext['stack'] = self._stack
        self.activeContext['method'] = self._method
        self.activeContext['receiver'] = self._receiver

    def readFromContext(self):
        self.pc = self.activeContext['pc']
        self.args = self.activeContext['args']
        self.tempvars = self.activeContext['tempvars']
        self._stack = self.activeContext['stack']
        self._receiver = self.activeContext['receiver']
        self._method = self.activeContext['method']

    @property
    def method(self):
        return self._method.yourself

    @property
    def receiver(self):
        return self._receiver.yourself

    @property
    def stack(self):
        return self._stack.yourself.directMemory

    def doPrimitive(self, primByte):
        r"""
        Perform a single primitive.
        # \x00    - integer add
        # \x01    - integer subtract
        # \x02    - integer multiply
        # \x03    - integer division
        # \x04    - integer comparison
        # \x05    - integer bitshift left
        # \x06    - integer bitshift right
        """
        if primByte == 0x00:
            # Primitive integer add
            arg2 = self.stack.pop()
            arg1 = self.stack.pop()
            self.stack.append(arg1 + arg2)
        elif primbyte == 0x01:
            # Primitive integer subtract
            arg2 = self.stack.pop()
            arg1 = self.stack.pop()
            self.stack.append(arg1 - arg2)
        elif primbyte == 0x02:
            # Primitive integer multiply
            arg2 = self.stack.pop()
            arg1 = self.stack.pop()
            self.stack.append(arg1 * arg2)
        elif primbyte == 0x03:
            # Primitive integer division
            arg2 = self.stack.pop()
            arg1 = self.stack.pop()
            self.stack.append(arg1 / arg2)
        elif primbyte == 0x04:
            # Primitive integer comparison
            arg2 = self.stack.pop()
            arg1 = self.stack.pop()
            if arg1 < arg2:
                self.stack.append(-1)
            elif arg1 == arg2:
                self.stack.append(0)
            else:
                self.stack.append(1)
        elif primbyte == 0x05:
            # Bitshift left
            arg2 = self.stack.pop()
            arg1 = self.stack.pop()
            self.stack.append(arg1 << arg2)
        elif primbyte == 0x06:
            # Bitshift right
            arg2 = self.stack.pop()
            arg1 = self.stack.pop()
            self.stack.append(arg1 >> arg2)

    def interpretOne(self):
        r"""
        Interpret a single bytecode.
        # QSIL Bytecode Manual
        # \x0_     - Stack Access
        # \x00     - pushRcvr
        # \x01 [0] - pushInst: [0]
        # \x02 [0] - pushArg: [0]
        # \x03 [0] - pushTemp: [0]
        # \x04 [0] - pushLiteral: [0]
        # \x05     - send
        # \x06     - returnTop
        # \x07 [0] - jump: [0]
        # \x08 [0] - jumpIfTrue: [0]
        # \x09 [0] - jumpIfFalse: [0]
        # \x0a [0] - popIntoInst: [0]
        # \x0b [0] - popIntoTemp: [0]
        # \x0c     - pop
        # \x0d [0] - debugStack: [0]
        # \x1_     - Primitive Access
        # \x10 [0] - doPrim: [0]
        """
        nextByte = self.method.directMemory[0][self.pc]
        if nextByte >= 0x00 and nextByte < 0x10:
            # Stack Access
            if nextByte == 0x00:
                # pushRcvr
                self.stack.append(Pointer(self.receiver.id))
            elif nextByte == 0x01:
                # pushInst: [0]
                self.pc += 1
                argN = self.method.directMemory[0][self.pc]
                self.stack.append(self.receiver.directMemory[argN])
            elif nextByte == 0x02:
                # pushArg:
                self.pc += 1
                argN = self.method.directMemory[0][self.pc]
                self.stack.append(self.args.directMemory[argN])
            elif nextByte == 0x03:
                # pushTemp:
                self.pc += 1
                argN = self.method.directMemory[0][self.pc]
                self.stack.append(self.tempvars.directMemory[argN])
            elif nextByte == 0x04:
                # pushLiteral:
                self.pc += 1
                argN = self.method.directMemory[0][self.pc]
                self.stack.append(self.method.directMemory[argN + 1])
            elif nextByte == 0x05:
                # send
                messageName = self.stack.pop()
                receiver = self.stack.pop()
                message = receiver.yourself[b'methods'].yourself[messageName]
                newContext = Object()
                newContext['pc'] = 0
                newContext['method'] = Pointer(message.id)
                newContext['receiver'] = Pointer(receiver.id)
                newContext['args'] = Object()
                newContext['tempvars'] = Object()
                newContext['stack'] = Object()
                for arg in range(len(messageName.split(b':')) - 1):
                    newContext['args'].directMemory.append(self.stack.pop())
                newContext['args'].directMemory.reverse()
                self.pushContext(newContext)
                return
            elif nextByte == 0x06:
                # returnTop
                returnValue = self.stack.pop()
                self.popContext()
                self.stack.append(returnValue)
            elif nextByte == 0x07:
                # jump:
                self.pc += 1
                argN = self.method.directMemory[0][self.pc]
                self.pc = argN - 1  # Minus one because we increment after this
            elif nextByte == 0x08:
                # jumpIfTrue:
                self.pc += 1
                toCheck = self.stack.pop()
                argN = self.method.directMemory[0][self.pc]
                if toCheck:
                    self.pc = argN - 1
            elif nextByte == 0x09:
                # jumpIfFalse:
                self.pc += 1
                toCheck = self.stack.pop()
                argN = self.method.directMemory[0][self.pc]
                if not toCheck:
                    self.pc = argN - 1
            elif nextByte == 0x0a:
                # popIntoInst:
                toPush = self.stack.pop()
                self.pc += 1
                argN = self.method.directMemory[0][self.pc]
                self.receiver.directMemory[argN] = toPush
            elif nextByte == 0x0b:
                # popIntoTemp:
                toPush = self.stack.pop()
                self.pc += 1
                argN = self.method.directMemory[0][self.pc]
                self.tempvars[argN] = toPush
            elif nextByte == 0x0c:
                # pop
                self.stack.pop()
            elif nextByte == 0x0d:
                # debugStack:
                self.pc += 1
                argN = self.method.directMemory[0][self.pc]
                print(self.stack[argN])
        elif nextByte >= 0x10 and nextByte < 0x20:
            # Primitive Access
            if nextByte == 0x10:
                # doPrim:
                self.pc += 1
                nextByte = self.method.directMemory[0][self.pc]
                self.doPrimitive(nextByte)
        else:
            raise ValueError("Unknown bytecode: %s", nextByte)
        self.pc += 1


def serializeObjects():
    r"""
    Serialize all the objects and return a bytes() object
    that can be used to load an exact copy of the current
    environment
    # File format:
    # \x00 - start object (id is next 6 chars)
    # \x01 - end object
    # \x02 - start/end object key
    # \x03 - start/end object value
    # \x04 - start int (32 bit)
    # \x05 - start float (actually a double)
    # \x06 - start/end pointer
    # \x07 - start/end string
    # (\x08) - escape next character
    """
    aStream = BytesIO()

    def writeSomething(anObject, printId=True):
        if isinstance(anObject, Pointer):
            aStream.write(b'\x06')
            aStream.write(anObject.id)
            aStream.write(b'\x06')
        elif isinstance(anObject, Object):
            aStream.write(b'\x00')
            if printId:
                aStream.write(anObject.id)
            for key, value in anObject.items():
                aStream.write(b'\x02')  # Begin key
                writeSomething(key, printId)
                aStream.write(b'\x03')  # Begin value
                writeSomething(value, printId)
            for aMemoryObject in anObject.directMemory:
                writeSomething(aMemoryObject, printId)
            aStream.write(b'\x01')
        elif isinstance(anObject, int):
            aStream.write(b'\x04')
            aStream.write(struct.pack('>i', anObject))
        elif isinstance(anObject, float):
            aStream.write(b'\x05')
            aStream.write(struct.pack('>d', anObject))
        elif isinstance(anObject, (str, bytes)):
            aStream.write(b'\x07')
            toWrite = b''
            for char in anObject:
                if char == 0x07:
                    toWrite += bytes([0x08])
                toWrite += bytes([char])
            aStream.write(toWrite)
            aStream.write(b'\x07')

    aStream.write(b'QSIL1')
    for anId, anObject in allobjects.items():
        writeSomething(anObject)

    aStream.write(b'\xab\xcd\xef')

    def writeContext(anObject):
        if 'pc' in anObject:
            aStream.write(b'ST')  # Context bytes
            aStream.write(struct.pack('>i', anObject['pc']))  # Encode pc
            aStream.write(anObject['method'].id)
            aStream.write(b'\x06')  # End pointer
            aStream.write(anObject['receiver'].id)
            aStream.write(b'\x06')  # End pointer
            writeSomething(anObject['args'], False)
            writeSomething(anObject['tempvars'], False)
            writeSomething(anObject['stack'], False)
            writeContext(anObject['homeContext'].yourself)
        else:
            # Write a blank object
            aStream.write(b'\x00')

    interp.saveToContext()  # Force a write of interpreter state variables
    writeContext(interp.activeContext.yourself)

    return aStream.getvalue()

allobjects = {}
interp = Interpreter()

starterBytes = (b'QSIL1'  # File header
                b'\x00'  # Start object 1
                b'\x00\x00\x00\x00\x00\x00'  # Object id (42-bit zero)
                b'\x07'  # Begin string (bytecodes)

                b'\x00'  # Push rcvr
                b'\x04\x01'  # Push lit 1
                b'\x05'  # Send
                b'\x0d\x00'  # Debug stack 0
                b'\x0c'  # Pop
                b'\x08\x07\x00'  # Jump to pc 0

                b'\x07'  # End string (bytecodes)
                b'\x06'  # Pointer to message receiver
                b'\x00\x00\x00\x00\x00\x01'  # ID of receiver (lit 0)
                b'\x06'  # End pointer to message receiver
                b'\x07'  # Begin string
                b'doTestTwo'  # Message to send (lit 1)
                b'\x07'  # End string
                b'\x01'  # End object 1

                b'\x00'  # Start object 2
                b'\x00\x00\x00\x00\x00\x09'  # Object id (42-bit nine)
                b'\x07'  # Begin string (bytecodes)

                b'\x04\x00'  # Push lit 0
                b'\x01\x00'  # Push inst var 0
                b'\x10\x00'  # Primitive: 0x00 (Int. Addition)
                b'\x0a\x00'  # Pop to instance var 0
                b'\x01\x00'  # Push inst var 0
                b'\x06'  # Return

                b'\x07'  # End string (bytecodes)
                b'\x04'  # Begin literal 0 (int)
                b'\x00\x00\x00\x01'  # Number (1)
                b'\x01'  # End object 2

                b'\x00'  # Start object 2 (receiver for test code)
                b'\x00\x00\x00\x00\x00\x01'  # Object id (42-bit one)
                b'\x02'  # Start key
                b'\x07'  # Begin string
                b'superclass'
                b'\x07'  # End string
                b'\x03'  # Begin value
                b'\x06'  # Begin pointer to class (OBJECT, with no superclass)
                b'\x00\x00\x00\x00\x00\x01'
                b'\x06'  # End pointer

                b'\x02'  # Start key
                b'\x07'  # Begin string
                b'className'
                b'\x07'  # End string
                b'\x03'  # Begin value
                b'\x07'  # Begin string (This is the OBJECT class)
                b'object'
                b'\x07'  # End pointer

                b'\x02'  # Start key
                b'\x07'  # Begin string
                b'methods'
                b'\x07'  # End string
                b'\x03'  # Begin value
                b'\x06'  # Begin pointer
                b'\x00\x00\x00\x00\x00\x02'
                b'\x06'  # End pointer

                # Instance variable 0
                b'\x04'  # Begin int
                b'\x00\x00\x00\x00'  # Number (0)

                b'\x01'  # End object 2 (receiver for test code)

                b'\x00'  # Begin object (array of methods with pointers)
                b'\x00\x00\x00\x00\x00\x02'  # Object id (42-bit two)
                b'\x02'  # Start key
                b'\x07'  # Begin string
                b'doTest'
                b'\x07'  # End key
                b'\x03'  # Begin value
                b'\x06'  # Begin pointer to method
                b'\x00\x00\x00\x00\x00\x00'
                b'\x06'  # End pointer to method
                b'\x02'  # Start key
                b'\x07'  # Begin string
                b'doTestTwo'
                b'\x07'  # End key
                b'\x03'  # Begin value
                b'\x06'  # Begin pointer to method
                b'\x00\x00\x00\x00\x00\x09'
                b'\x06'  # End pointer to method
                b'\x01'  # End object (array of methods with pointers)

                b'\xab\xcd\xef'  # Separator for live memory

                b'ST'  # Context bytes. Means that there is a context to read
                b'\x00\x00\x00\x00'  # pc
                b'\x00\x00\x00\x00\x00\x00'  # ID of method
                b'\x06'  # End pointer to method
                b'\x00\x00\x00\x00\x00\x01'  # ID of receiver
                b'\x06'  # End pointer to receiver
                b'\x00'  # Begin args object
                b'\x01'  # End args object
                b'\x00'  # Begins tempVars object
                b'\x01'  # End tempVars object
                b'\x00'  # Begin stack object
                b'\x01'  # End stack object
                b'\x00'  # Begin final context (blank, no context byte)
                )

if __name__ == '__main__':
    try:
        with open('test.image', 'rb') as b:
            x = b.read()
            starterBytes = x
        read(starterBytes)  # Some test code
        rehashObjects()
        while True:
            # This seems redundant, and useless, because this is just
            # running a function normally, but this is important because
            # it prevents Control+C from pausing in the middle of an
            # operation, which helps to prevent corrupted contexts on a
            # save. When a primitive is added for saving, then this
            # can be removed.
            target = threading.Thread(target=interp.interpretOne)
            target.start()
            target.join()
    finally:
        with open('test.image', 'wb') as b:
            # This will exist until a primitive is added for saving
            b.write(serializeObjects())
