import cv2
import mediapipe as mp
import pyautogui
import math
import time
from enum import IntEnum
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from google.protobuf.json_format import MessageToDict
import screen_brightness_control as sbcontrol

pyautogui.FAILSAFE = False
mp_drawing = mp.solutions.drawing_utils
mp_hands = mp.solutions.hands


class Gest(IntEnum):
    FIST = 0
    PINKY = 1
    RING = 2
    MID = 4
    LAST3 = 7
    INDEX = 8
    FIRST2 = 12
    LAST4 = 15
    THUMB = 16
    PALM = 31
    V_GEST = 33
    TWO_FINGER_CLOSED = 34
    PINCH_MAJOR = 35
    PINCH_MINOR = 36


class HLabel(IntEnum):
    MINOR = 0
    MAJOR = 1


class SystemState(IntEnum):
    LOCKED = 0
    ACTIVE = 1
    STOPPED = 2


class HandRecog:
    def __init__(self, hand_label):
        self.finger = 0
        self.ori_gesture = Gest.PALM
        self.prev_gesture = Gest.PALM
        self.frame_count = 0
        self.hand_result = None
        self.hand_label = hand_label

    def update_hand_result(self, hand_result):
        self.hand_result = hand_result

    def get_signed_dist(self, point):
        sign = -1
        if self.hand_result.landmark[point[0]].y < self.hand_result.landmark[point[1]].y:
            sign = 1
        dist = (self.hand_result.landmark[point[0]].x -
                self.hand_result.landmark[point[1]].x) ** 2
        dist += (self.hand_result.landmark[point[0]].y -
                 self.hand_result.landmark[point[1]].y) ** 2
        return math.sqrt(dist) * sign

    def get_dist(self, point):
        dist = (self.hand_result.landmark[point[0]].x -
                self.hand_result.landmark[point[1]].x) ** 2
        dist += (self.hand_result.landmark[point[0]].y -
                 self.hand_result.landmark[point[1]].y) ** 2
        return math.sqrt(dist)

    def get_dz(self, point):
        return abs(self.hand_result.landmark[point[0]].z - self.hand_result.landmark[point[1]].z)

    def set_finger_state(self):
        if self.hand_result is None:
            return

        points = [[8, 5, 0], [12, 9, 0], [16, 13, 0], [20, 17, 0]]
        self.finger = 0
        self.finger = self.finger | 0
        for point in points:
            dist = self.get_signed_dist(point[:2])
            dist2 = self.get_signed_dist(point[1:])
            ratio = round(dist / dist2, 1) if abs(dist2) > 1e-6 else 999.0
            self.finger = self.finger << 1
            if ratio > 0.5:
                self.finger = self.finger | 1

    def get_gesture(self):
        if self.hand_result is None:
            return Gest.PALM

        current_gesture = Gest.PALM
        if self.finger in [Gest.LAST3, Gest.LAST4] and self.get_dist([8, 4]) < 0.1:
            current_gesture = Gest.PINCH_MINOR if self.hand_label == HLabel.MINOR else Gest.PINCH_MAJOR
        elif self.finger == Gest.FIRST2:
            dist1 = self.get_dist([8, 12])
            dist2 = self.get_dist([5, 9])
            ratio = dist1 / dist2 if abs(dist2) > 1e-6 else 999.0
            if ratio > 1.7:
                current_gesture = Gest.V_GEST
            else:
                if self.get_dz([8, 12]) < 0.1:
                    current_gesture = Gest.TWO_FINGER_CLOSED
                else:
                    current_gesture = Gest.MID
        else:
            # In this project, thumb state is not explicitly encoded in set_finger_state(),
            # so a fully open hand is typically detected as LAST4 instead of PALM.
            # Normalize LAST4 to PALM so authentication and emergency exit work with
            # a real open-hand gesture.
            if self.finger == Gest.LAST4:
                current_gesture = Gest.PALM
            else:
                try:
                    current_gesture = Gest(self.finger)
                except ValueError:
                    current_gesture = Gest.PALM

        if current_gesture == self.prev_gesture:
            self.frame_count += 1
        else:
            self.frame_count = 0
        self.prev_gesture = current_gesture

        if self.frame_count > 4:
            self.ori_gesture = current_gesture

        try:
            return Gest(self.ori_gesture)
        except ValueError:
            return Gest.PALM


class Controller:
    flag = False
    grabflag = False
    pinchmajorflag = False
    pinchminorflag = False
    pinchstartxcoord = None
    pinchstartycoord = None
    pinchdirectionflag = None
    prevpinchlv = 0
    pinchlv = 0
    framecount = 0
    prev_hand = None
    pinch_threshold = 0.15

    @staticmethod
    def reset_flags():
        Controller.flag = False
        Controller.grabflag = False
        Controller.pinchmajorflag = False
        Controller.pinchminorflag = False
        Controller.pinchstartxcoord = None
        Controller.pinchstartycoord = None
        Controller.pinchdirectionflag = None
        Controller.prevpinchlv = 0
        Controller.pinchlv = 0
        Controller.framecount = 0
        Controller.prev_hand = None
        try:
            pyautogui.mouseUp(button="left")
        except Exception:
            pass

    @staticmethod
    def getpinchylv(hand_result):
        return round((Controller.pinchstartycoord - hand_result.landmark[8].y) * 10, 1)

    @staticmethod
    def getpinchxlv(hand_result):
        return round((hand_result.landmark[8].x - Controller.pinchstartxcoord) * 10, 1)

    @staticmethod
    def changesystembrightness():
        current = sbcontrol.get_brightness()
        current_value = current[0] if isinstance(current, list) else current
        currentBrightnessLv = current_value / 100.0
        currentBrightnessLv += Controller.pinchlv / 20.0
        currentBrightnessLv = max(0.0, min(1.0, currentBrightnessLv))
        sbcontrol.fade_brightness(
            int(100 * currentBrightnessLv), start=current_value)

    @staticmethod
    def changesystemvolume():
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(
            IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        currentVolumeLv = volume.GetMasterVolumeLevelScalar()
        currentVolumeLv += Controller.pinchlv / 20.0
        currentVolumeLv = max(0.0, min(1.0, currentVolumeLv))
        volume.SetMasterVolumeLevelScalar(currentVolumeLv, None)

    @staticmethod
    def scrollVertical():
        pyautogui.scroll(120 if Controller.pinchlv > 0.0 else -120)

    @staticmethod
    def scrollHorizontal():
        try:
            pyautogui.hscroll(-120 if Controller.pinchlv > 0.0 else 120)
        except Exception:
            pyautogui.keyDown('shift')
            pyautogui.scroll(-120 if Controller.pinchlv > 0.0 else 120)
            pyautogui.keyUp('shift')

    @staticmethod
    def get_position(hand_result):
        point = 9
        position = [hand_result.landmark[point].x,
                    hand_result.landmark[point].y]
        sx, sy = pyautogui.size()
        x_old, y_old = pyautogui.position()
        x = int(position[0] * sx)
        y = int(position[1] * sy)

        if Controller.prev_hand is None:
            Controller.prev_hand = (x, y)

        delta_x = x - Controller.prev_hand[0]
        delta_y = y - Controller.prev_hand[1]
        distsq = delta_x ** 2 + delta_y ** 2
        Controller.prev_hand = [x, y]

        if distsq <= 25:
            ratio = 0
        elif distsq <= 900:
            ratio = 0.07 * (distsq ** 0.5)
        else:
            ratio = 2.1

        return x_old + delta_x * ratio, y_old + delta_y * ratio

    @staticmethod
    def pinch_control_init(hand_result):
        Controller.pinchstartxcoord = hand_result.landmark[8].x
        Controller.pinchstartycoord = hand_result.landmark[8].y
        Controller.pinchlv = 0
        Controller.prevpinchlv = 0
        Controller.framecount = 0

    @staticmethod
    def pinch_control(hand_result, controlHorizontal, controlVertical):
        if Controller.framecount >= 2:
            Controller.framecount = 0
            Controller.pinchlv = (Controller.pinchlv +
                                  Controller.prevpinchlv) / 2
            if Controller.pinchdirectionflag is True:
                controlHorizontal()
            elif Controller.pinchdirectionflag is False:
                controlVertical()

        lvx = Controller.getpinchxlv(hand_result)
        lvy = Controller.getpinchylv(hand_result)
        if abs(lvy) > abs(lvx) and abs(lvy) > Controller.pinch_threshold:
            Controller.pinchdirectionflag = False
            if abs(Controller.prevpinchlv - lvy) < Controller.pinch_threshold:
                Controller.framecount += 1
            else:
                Controller.prevpinchlv = lvy
                Controller.framecount = 0
        elif abs(lvx) > Controller.pinch_threshold:
            Controller.pinchdirectionflag = True
            if abs(Controller.prevpinchlv - lvx) < Controller.pinch_threshold:
                Controller.framecount += 1
            else:
                Controller.prevpinchlv = lvx
                Controller.framecount = 0

    @staticmethod
    def handle_controls(gesture, hand_result):
        x, y = None, None
        if gesture != Gest.PALM:
            x, y = Controller.get_position(hand_result)

        if gesture != Gest.FIST and Controller.grabflag:
            Controller.grabflag = False
            pyautogui.mouseUp(button="left")
        if gesture != Gest.PINCH_MAJOR and Controller.pinchmajorflag:
            Controller.pinchmajorflag = False
        if gesture != Gest.PINCH_MINOR and Controller.pinchminorflag:
            Controller.pinchminorflag = False

        if gesture == Gest.V_GEST:
            Controller.flag = True
            pyautogui.moveTo(x, y, duration=0.1)
        elif gesture == Gest.FIST:
            if not Controller.grabflag:
                Controller.grabflag = True
                pyautogui.mouseDown(button="left")
            pyautogui.moveTo(x, y, duration=0.1)
        elif gesture == Gest.MID and Controller.flag:
            pyautogui.click()
            Controller.flag = False
        elif gesture == Gest.INDEX and Controller.flag:
            pyautogui.click(button='right')
            Controller.flag = False
        elif gesture == Gest.TWO_FINGER_CLOSED and Controller.flag:
            pyautogui.doubleClick()
            Controller.flag = False
        elif gesture == Gest.PINCH_MINOR:
            if not Controller.pinchminorflag:
                Controller.pinch_control_init(hand_result)
                Controller.pinchminorflag = True
            Controller.pinch_control(
                hand_result, Controller.scrollHorizontal, Controller.scrollVertical)
        elif gesture == Gest.PINCH_MAJOR:
            if not Controller.pinchmajorflag:
                Controller.pinch_control_init(hand_result)
                Controller.pinchmajorflag = True
            Controller.pinch_control(
                hand_result, Controller.changesystembrightness, Controller.changesystemvolume)


class GestureController:
    def __init__(self):
        self.cap = cv2.VideoCapture(0)
        self.gc_mode = True
        self.dom_hand = True
        self.system_state = SystemState.LOCKED

        self.handmajor = HandRecog(HLabel.MAJOR)
        self.handminor = HandRecog(HLabel.MINOR)
        self.hr_major = None
        self.hr_minor = None

        # Authentication sequence: PALM -> INDEX -> FIST
        self.auth_sequence = [Gest.PALM, Gest.INDEX, Gest.FIST]
        self.auth_step_index = 0
        self.auth_hold_frames_needed = 6
        self.auth_hold_counter = 0
        self.auth_cooldown_frames_needed = 6
        self.auth_cooldown_counter = 0
        self.auth_feedback = "Authentication required"

        # Emergency exit: hold a real PALM gesture for 3 seconds after unlock.
        # Time-based tracking is more reliable than frame counts because webcam FPS can vary.
        self.exit_hold_seconds_needed = 3.0
        self.exit_hold_start_time = None
        self.authenticated_at = None
        self.exit_grace_period_seconds = 1.5

        self.last_detected_major = None
        self.last_detected_minor = None

    @staticmethod
    def gesture_name(gesture):
        return gesture.name if isinstance(gesture, Gest) else "NONE"

    def stop_controller(self):
        self.gc_mode = False
        self.system_state = SystemState.STOPPED
        Controller.reset_flags()
        self.cap.release()
        cv2.destroyAllWindows()

    def stop_controller(self):
        self.gc_mode = 0
        self.system_state = SystemState.STOPPED
        Controller.reset_flags()

    def classify_hands(self, results):
        left, right = None, None
        for idx in range(len(results.multi_hand_landmarks)):
            try:
                handedness_dict = MessageToDict(results.multi_handedness[idx])
                label = handedness_dict['classification'][0]['label']
                if label == 'Right':
                    right = results.multi_hand_landmarks[idx]
                else:
                    left = results.multi_hand_landmarks[idx]
            except Exception:
                pass
        if self.dom_hand:
            self.hr_major = right
            self.hr_minor = left
        else:
            self.hr_major = left
            self.hr_minor = right

    def process_authentication(self, major_gesture, minor_gesture):
        expected = self.auth_sequence[self.auth_step_index]

        # Short cooldown after each accepted step so the user can change pose.
        if self.auth_cooldown_counter > 0:
            self.auth_cooldown_counter -= 1
            self.auth_hold_counter = 0
            self.auth_feedback = "Step accepted. Change pose, then show the next gesture."
            return

        matched = (major_gesture == expected) or (minor_gesture == expected)
        if matched:
            self.auth_hold_counter += 1
            self.auth_feedback = "Hold current authentication gesture..."
            if self.auth_hold_counter >= self.auth_hold_frames_needed:
                self.auth_step_index += 1
                self.auth_hold_counter = 0
                self.auth_cooldown_counter = self.auth_cooldown_frames_needed

                if self.auth_step_index >= len(self.auth_sequence):
                    self.system_state = SystemState.ACTIVE
                    self.authenticated_at = time.time()
                    self.exit_hold_counter = 0
                    self.auth_feedback = "Authentication successful"
                    Controller.reset_flags()
                    return

                self.auth_feedback = "Step accepted. Change pose, then show the next gesture."
        else:
            self.auth_hold_counter = 0
            self.auth_feedback = "Waiting for next authentication gesture..."

    def process_emergency_exit(self, major_gesture, minor_gesture, major_present, minor_present):
        # Exit is available only after the user has authenticated and the short
        # post-authentication grace period has passed.
        if self.system_state != SystemState.ACTIVE:
            self.exit_hold_start_time = None
            return

        if self.authenticated_at is None or (time.time() - self.authenticated_at < self.exit_grace_period_seconds):
            self.exit_hold_start_time = None
            return

        # Count exit only when a REAL detected hand is recognized as PALM.
        # This avoids the old bug where missing/unclassified hands defaulted to PALM
        # and accidentally advanced the exit counter.
        major_palm = major_present and (major_gesture == Gest.PALM)
        minor_palm = minor_present and (minor_gesture == Gest.PALM)
        palm_seen = major_palm or minor_palm

        if palm_seen:
            if self.exit_hold_start_time is None:
                self.exit_hold_start_time = time.time()
            elif (time.time() - self.exit_hold_start_time) >= self.exit_hold_seconds_needed:
                self.stop_controller()
        else:
            self.exit_hold_start_time = None

    def draw_ui(self, image, major_gesture, minor_gesture):
        major_name = major_gesture.name if isinstance(
            major_gesture, Gest) else "NONE"
        minor_name = minor_gesture.name if isinstance(
            minor_gesture, Gest) else "NONE"

        cv2.putText(image, f"State: {self.system_state.name}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
        if self.system_state == SystemState.LOCKED:
            cv2.putText(image, "Authentication required", (20, 85),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
            cv2.putText(image, self.auth_feedback, (20, 125),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 200, 0), 2)
            cv2.putText(image, f"Detected: Major={major_name}, Minor={minor_name}", (20, 165),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 220, 255), 2)
            cv2.putText(image, "Keyboard exit: ENTER or Q", (20, 200),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 180, 180), 2)
        else:
            cv2.putText(image, f"Major: {major_name} | Minor: {minor_name}", (20, 85),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
            cv2.putText(image, "Emergency exit: hold PALM for 3 seconds", (20, 125),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 255, 180), 2)
            if self.exit_hold_start_time is not None:
                elapsed = max(0.0, time.time() - self.exit_hold_start_time)
                cv2.putText(image, f"Exit hold progress: {elapsed:.1f}/{self.exit_hold_seconds_needed:.1f} sec", (20, 165),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 220, 255), 2)

    def start(self):
        with mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.5, min_tracking_confidence=0.5) as hands:
            while self.cap.isOpened() and self.gc_mode:
                success, image = self.cap.read()
                if not success:
                    continue

                image = cv2.cvtColor(cv2.flip(image, 1), cv2.COLOR_BGR2RGB)
                image.flags.writeable = False
                results = hands.process(image)
                image.flags.writeable = True
                image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

                major_gesture = None
                minor_gesture = None
                major_present = False
                minor_present = False

                if results.multi_hand_landmarks:
                    self.classify_hands(results)
                    self.handmajor.update_hand_result(self.hr_major)
                    self.handminor.update_hand_result(self.hr_minor)

                    if self.hr_major is not None:
                        major_present = True
                        self.handmajor.set_finger_state()
                        major_gesture = self.handmajor.get_gesture()
                    if self.hr_minor is not None:
                        minor_present = True
                        self.handminor.set_finger_state()
                        minor_gesture = self.handminor.get_gesture()

                    self.last_detected_major = major_gesture
                    self.last_detected_minor = minor_gesture

                    if self.system_state == SystemState.LOCKED:
                        self.process_authentication(
                            major_gesture, minor_gesture)
                    elif self.system_state == SystemState.ACTIVE:
                        if minor_gesture == Gest.PINCH_MINOR and self.handminor.hand_result is not None:
                            Controller.handle_controls(
                                minor_gesture, self.handminor.hand_result)
                        elif major_gesture == Gest.PINCH_MAJOR and self.handmajor.hand_result is not None:
                            Controller.handle_controls(
                                major_gesture, self.handmajor.hand_result)
                        elif self.handmajor.hand_result is not None:
                            Controller.handle_controls(
                                major_gesture, self.handmajor.hand_result)
                        elif self.handminor.hand_result is not None:
                            Controller.handle_controls(
                                minor_gesture, self.handminor.hand_result)
                        self.process_emergency_exit(
                            major_gesture, minor_gesture, major_present, minor_present)

                    for hand_landmarks in results.multi_hand_landmarks:
                        mp_drawing.draw_landmarks(
                            image, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                else:
                    Controller.prev_hand = None
                    self.hr_major = None
                    self.hr_minor = None
                    if self.system_state == SystemState.LOCKED:
                        self.auth_hold_counter = 0
                        self.auth_feedback = "Waiting for next authentication gesture..."
                    elif self.system_state == SystemState.ACTIVE:
                        self.exit_hold_start_time = None

                self.draw_ui(image, major_gesture, minor_gesture)
                cv2.imshow('Gesture Controller', image)

                key = cv2.waitKey(5) & 0xFF
                if key == 13 or key == ord('q'):
                    self.stop_controller()
                    break

        self.cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    gc1 = GestureController()
    gc1.start()
