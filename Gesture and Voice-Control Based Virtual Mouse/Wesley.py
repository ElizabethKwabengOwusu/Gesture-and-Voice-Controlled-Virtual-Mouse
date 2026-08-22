import pyttsx3
import speech_recognition as sr
from datetime import date
import time
import webbrowser
import datetime
from pynput.keyboard import Key, Controller
import pyautogui
import sys
import os
from os import listdir
from os.path import isfile, join
import importlib.util
from pathlib import Path
from threading import Thread
import app

# ---------------- Gesture Controller Loader ----------------
Gesture_Controller = None
gesture_thread = None
gc = None

for candidate in [
    'Enhanced_Gesture_Controller_v2_fixed_safe3.py',
    'Enhanced_Gesture_Controller_v2_fixed_safe2.py',
    'Enhanced_Gesture_Controller_v2_fixed.py',
    'Enhanced_Gesture_Controller_v2.py',
    'Enhanced_Gesture_Controller.py',
    'Gesture_Controller.py',
]:
    path = Path(candidate)
    if path.exists():
        spec = importlib.util.spec_from_file_location(
            'Gesture_Controller', str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        Gesture_Controller = module
        break

# ---------------- Initialization ----------------
today = date.today()
r = sr.Recognizer()
keyboard = Controller()

engine = pyttsx3.init()
voices = engine.getProperty('voices')
engine.setProperty('voice', voices[0].id)

file_exp_status = False
files = []
path = ''

# ---------------- Functions ----------------


def reply(audio):
    app.ChatBot.addAppMsg(audio)
    print(audio)
    engine.say(audio)
    engine.runAndWait()


def wish():
    hour = int(datetime.datetime.now().hour)
    if 0 <= hour < 12:
        reply("Good Morning!")
    elif 12 <= hour < 18:
        reply("Good Afternoon!")
    else:
        reply("Good Evening!")
    reply("I am Wesley, how can I assist you today?")


def record_audio():
    with sr.Microphone() as source:
        r.pause_threshold = 0.8
        r.adjust_for_ambient_noise(source, duration=0.5)

        try:
            print("Listening...")
            audio = r.listen(source, timeout=15, phrase_time_limit=15)
            voice_data = r.recognize_google(audio)
            print("You said:", voice_data)
            return voice_data.lower()

        except sr.UnknownValueError:
            print("Could not understand")
            return ""

        except sr.RequestError:
            reply("Network error")
            return ""

        except Exception as e:
            print("Error:", e)
            return ""

# ---------------- Gesture Control ----------------


def start_gesture_system():
    global gc, gesture_thread

    if Gesture_Controller is None:
        return "Gesture controller not found"

    if gc and gc.gc_mode:
        return "Gesture controller already running"

    try:
        gc = Gesture_Controller.GestureController()
        gesture_thread = Thread(target=gc.start, daemon=True)
        gesture_thread.start()
        return "Gesture recognition started"
    except Exception as e:
        return f"Error starting gesture system: {e}"


def stop_gesture_system():
    global gc

    if Gesture_Controller is None:
        return "Gesture controller not found"

    if gc and gc.gc_mode:
        try:
            gc.stop_controller()
            return "Gesture recognition stopped"
        except Exception as e:
            return f"Error stopping gesture system: {e}"
    else:
        return "Gesture recognition already stopped"


# ---------------- Command Processing ----------------


def respond(voice_data):
    global file_exp_status, files, path

    print("Command:", voice_data)

    # MUST include Wesley
    if not any(name in voice_data for name in ['wesley', 'wesli', 'westly', 'wezly']):
        return

    for name in ['wesley', 'wesli', 'westly', 'wezly']:
        voice_data = voice_data.replace(name, '').strip()

    app.eel.addUserMsg(voice_data)

    if voice_data == "":
        return

    # -------- BASIC --------
    if 'hello' in voice_data:
        wish()

    elif 'name' in voice_data:
        reply('My name is Wesley!')

    elif 'date' in voice_data:
        reply(today.strftime("%B %d, %Y"))

    elif 'time' in voice_data:
        reply(str(datetime.datetime.now()).split(" ")[1].split('.')[0])

    elif 'open file manager' in voice_data:
        os.system('explorer')
        reply('Opening file manager')

    # -------- WEB --------
    elif 'search' in voice_data:
        query = voice_data.replace('search', '').strip()
        reply('Searching ' + query)
        webbrowser.open(f"https://google.com/search?q={query}")

    elif 'location' in voice_data:
        reply('Which place?')
        place = record_audio()
        if place:
            webbrowser.open(f"https://google.com/maps/place/{place}")
            reply('Opening location')

    # -------- GESTURE --------
    elif 'start gesture controller' in voice_data:
        reply(start_gesture_system())

    elif 'stop gesture controller' in voice_data:
        reply(stop_gesture_system())

    # -------- KEYBOARD --------
    elif 'copy' in voice_data:
        with keyboard.pressed(Key.ctrl):
            keyboard.press('c')
            keyboard.release('c')
        reply('Copied')

    elif 'paste' in voice_data:
        with keyboard.pressed(Key.ctrl):
            keyboard.press('v')
            keyboard.release('v')
        reply('Pasted')

    # -------- FILE SYSTEM --------
    elif 'list' in voice_data:
        path = 'C://'
        files = listdir(path)
        file_exp_status = True

        filestr = ""
        for i, f in enumerate(files, start=1):
            filestr += f"{i}: {f}<br>"

        reply('Here are your files')
        app.ChatBot.addAppMsg(filestr)

    elif file_exp_status:
        if 'open' in voice_data:
            try:
                index = int(voice_data.split()[-1]) - 1
                selected = files[index]

                full_path = os.path.join(path, selected)

                if isfile(full_path):
                    os.startfile(full_path)
                else:
                    path = full_path + "//"
                    files = listdir(path)

                reply("Opened")

            except:
                reply("Invalid selection")

    # -------- EXIT --------
    elif 'exit' in voice_data:
        stop_gesture_system()
        reply('Exiting')
        sys.exit()

    else:
        reply("I didn't understand that")


# ---------------- MAIN ----------------
t1 = Thread(target=app.ChatBot.start)
t1.start()

while not app.ChatBot.started:
    time.sleep(0.5)

wish()

while True:
    if app.ChatBot.isUserInput():
        voice_data = app.ChatBot.popUserInput().lower()
    else:
        voice_data = record_audio()

    if voice_data != "":
        try:
            respond(voice_data)
        except Exception as e:
            print("Error:", e)

    time.sleep(0.5)
