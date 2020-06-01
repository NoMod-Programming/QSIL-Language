# QSIL-Language
Quick, Self-Interpreting Language, or "Random Project for my Boredom"

This is a (hopefully) self-interpreting language that should, after some more development, be capable of compiling its own bytecodes for itself. To get it running, download the code, and in a terminal (or cmd for windows users), type:

    python3 qsilboostrapper.py
    python3 qsilInterpreter.py

Right now, all this does is print a single `Association` object and its instance variables, then run "1 + 1" in a loop for a bit to get an idea of the number of instructions processed (on average) per second. 