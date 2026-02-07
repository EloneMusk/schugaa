import warnings
warnings.simplefilter("ignore")

import rumps
import json
import threading
import os
import sys
import time
import math
from libre_api import LibreClient
from AppKit import (NSImage, NSApplication, NSMenu, NSMenuItem, NSObject, NSView, NSBezierPath, 
                   NSTrackingArea, NSTextField, NSColor, NSFont, NSString,
                   NSTrackingMouseEnteredAndExited, NSTrackingMouseMoved, 
                   NSTrackingActiveInKeyWindow, NSTrackingActiveAlways, NSTrackingInVisibleRect,
                   NSMutableAttributedString, NSFontAttributeName, NSForegroundColorAttributeName,
                   NSParagraphStyleAttributeName, NSMutableParagraphStyle, NSWorkspace,
                   NSVisualEffectView, NSVisualEffectMaterialHUDWindow, NSVisualEffectBlendingModeBehindWindow,
                   NSVisualEffectStateActive, NSVisualEffectMaterialPopover, NSAppearance)
from Foundation import NSMakeRect, NSURL, NSUserDefaults
import objc
warnings.filterwarnings("ignore", category=objc.ObjCPointerWarning)

MMOL_FACTOR = 18.0182

def _get_keyring():
    try:
        import keyring  
        return keyring
    except Exception:
        return None

def get_keyring_password(email):
    keyring = _get_keyring()
    if not keyring or not email:
        return None
    try:
        return keyring.get_password("schugaa", email)
    except Exception:
        return None

def set_keyring_password(email, password):
    keyring = _get_keyring()
    if not keyring or not email or not password:
        return False
    try:
        keyring.set_password("schugaa", email, password)
        return True
    except Exception:
        return False

def delete_keyring_password(email):
    keyring = _get_keyring()
    if not keyring or not email:
        return False
    try:
        keyring.delete_password("schugaa", email)
        return True
    except Exception:
        return False

def unit_factor(unit):
    return MMOL_FACTOR if unit == "mmol/L" else 1.0

def to_display_value(value, unit):
    if unit == "mmol/L":
        return value / MMOL_FACTOR
    return value

def write_json_secure(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

from datetime import datetime
import queue

def set_dock_icon():
    try:
        icon_path = resource_path("Schugaa.icns")
        if not os.path.exists(icon_path):
             icon_path = resource_path("glycemic-index.png")
             
        if os.path.exists(icon_path):
            image = NSImage.alloc().initWithContentsOfFile_(icon_path)
            if image:
                NSApplication.sharedApplication().setApplicationIconImage_(image)
    except Exception as e:
        pass

class MenuActionHandler(NSObject):
    def initWithApp_(self, app):
        self = objc.super(MenuActionHandler, self).init()
        self.app = app
        return self
    
    def refresh_(self, sender):
        self.app.refresh_now(sender)
        
    def logout_(self, sender):
        self.app.logout(sender)
        
    def quit_(self, sender):
        rumps.quit_application()

    def setUnitMgdl_(self, sender):
        self.app.set_unit("mg/dL")

    def setUnitMmol_(self, sender):
        self.app.set_unit("mmol/L")

    def donate_(self, sender):
        NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_("https://ko-fi.com/abhishek0978"))

    def shareDebugLogs_(self, sender):
        if os.path.exists(log_path):
             NSWorkspace.sharedWorkspace().selectFile_inFileViewerRootedAtPath_(log_path, None)
        else:
             print("Log file not found.")

class ThemeChangeObserver(NSObject):
    def initWithApp_(self, app):
        self = objc.super(ThemeChangeObserver, self).init()
        self.app = app
        return self
    
    def themeChanged_(self, notification):
        # We need to run this on the main thread to be safe with UI updates
        # although Rumos/PyObjC usually handles this, explicit dispatch is safer if coming from a distributed notification
        self.app.update_status_bar_appearance()
        if hasattr(self.app, 'graph_view'):
            self.app.graph_view.setNeedsDisplay_(True)

class GraphPlotView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(GraphPlotView, self).initWithFrame_(frame)
        if self:

            self.data_points = []
            self.hover_point = None
            self.unit = "mg/dL"
            
            options = (NSTrackingMouseEnteredAndExited | 
                      NSTrackingMouseMoved | 
                      NSTrackingActiveInKeyWindow | 
                      NSTrackingActiveAlways |
                      NSTrackingInVisibleRect)
            tracking_area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
                self.bounds(), options, self, None)
            self.addTrackingArea_(tracking_area)
            
            self.tooltip_container = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 105, 50))
            self.tooltip_container.setWantsLayer_(True)
            
            light_blue = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.85, 0.91, 0.98, 0.95)
            self.tooltip_container.layer().setBackgroundColor_(light_blue.CGColor())
            self.tooltip_container.layer().setCornerRadius_(8)
            self.tooltip_container.layer().setBorderWidth_(1.0)
            border_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.75, 0.82, 0.92, 1.0)
            self.tooltip_container.layer().setBorderColor_(border_color.CGColor())
            self.tooltip_container.setHidden_(True)
            
            self.tooltip_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 5, 105, 40))
            self.tooltip_label.setBezeled_(False)
            self.tooltip_label.setDrawsBackground_(False)
            self.tooltip_label.setBackgroundColor_(NSColor.clearColor())
            self.tooltip_label.setEditable_(False)
            self.tooltip_label.setSelectable_(False)
            self.tooltip_label.setAlignment_(1)  
            
            self.tooltip_container.addSubview_(self.tooltip_label)
            self.addSubview_(self.tooltip_container)
            


            self.trend = 3 
            self.stats = {"low": 0, "in_range": 0, "high": 0}
            
        return self

    def calculate_stats(self):
        if not self.data_points:
            self.stats = {"low": 0, "in_range": 0, "high": 0}
            return

        total = len(self.data_points)
        low_count = 0
        in_range_count = 0
        high_count = 0
        
        
        
        unit = getattr(self, 'unit', 'mg/dL')
        is_mmol = unit == 'mmol/L'
        
        limit_low = 3.9 if is_mmol else 70
        limit_high = 10.0 if is_mmol else 180
        
        for val, _ in self.data_points:
            
            
            if val < 70:
                low_count += 1
            elif val > 180:
                high_count += 1
            else:
                in_range_count += 1
                
        self.stats = {
            "low": int((low_count / total) * 100),
            "in_range": int((in_range_count / total) * 100),
            "high": int((high_count / total) * 100)
        }

    def is_dark_mode(self):
        """Check if system is in dark mode using effectiveAppearance"""
        try:
            # Try to get appearance from self (view)
            appearance = self.effectiveAppearance()
            if appearance:
                 if "Dark" in appearance.name():
                     return True
            
            # Fallback to NSApp
            if hasattr(NSApplication, 'sharedApplication'):
                app = NSApplication.sharedApplication()
                if app:
                     return "Dark" in app.effectiveAppearance().name()
                     
            style = NSUserDefaults.standardUserDefaults().stringForKey_("AppleInterfaceStyle")
            is_dark = (style == "Dark")
            return is_dark
        except:
            pass
        return False

    def get_color(self, value):
        if value < 70:
            return NSColor.redColor()
        elif 70 <= value <= 79:
            return NSColor.yellowColor()
        elif 80 <= value <= 180:
            return NSColor.greenColor()
        elif 181 <= value <= 220:
            return NSColor.yellowColor()
        elif 221 <= value <= 250:
            return NSColor.orangeColor()
        else: 
            return NSColor.redColor()

    def set_trend(self, trend):
        self.trend = trend
        self.setNeedsDisplay_(True)

    def update_data(self, data):
        self.data_points = []
        try:
            for point in data:
                val = point.get("Value")
                ts = point.get("Timestamp")
                if val:
                    self.data_points.append((val, ts))
            
            if len(self.data_points) > 100:
                 self.data_points = self.data_points[-100:]
                 
        except Exception as e:
            print(f"Error parsing graph data: {e}")
            
        self.calculate_stats() 
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        if not self.data_points:
             return

        is_dark = self.is_dark_mode()
        
        if is_dark:
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.05, 0.05, 0.05, 1.0).set()
        else:
            NSColor.whiteColor().set()
        NSBezierPath.fillRect_(self.bounds())
        
        width = rect.size.width
        height = rect.size.height
        
        unit = getattr(self, 'unit', 'mg/dL')
        is_mmol = unit == 'mmol/L'
        factor = unit_factor(unit)
        
        if is_mmol:
            max_y_val = 21.0
            min_y_val = 0.0
            grid_values = [3, 6, 9, 12, 15, 18, 21] 
            val_70 = 3.9
            val_180 = 10.0
        else:
            max_y_val = 300 
            min_y_val = 50 
            grid_values = [50, 100, 150, 200, 250, 300]
            val_70 = 70
            val_180 = 180

        y_range = max_y_val - min_y_val
        
        margin_left = 45 
        margin_right = 20
        margin_top = 20 
        margin_bottom = 75 
        
        plot_width = width - margin_left - margin_right
        plot_height = height - margin_bottom - margin_top
        
        def get_y(val):
            val_clamped = max(min(val, max_y_val), min_y_val)
            normalized = (val_clamped - min_y_val) / y_range
            return margin_bottom + normalized * plot_height

        def get_x(index, total):
            step = plot_width / max(total - 1, 1) if total > 1 else 0
            return margin_left + index * step

        y_low = get_y(val_70)
        y_high = get_y(val_180)
        
        if y_high > y_low:
             band_rect = NSMakeRect(margin_left, y_low, plot_width, y_high - y_low)
             if is_dark:
                 NSColor.colorWithCalibratedRed_green_blue_alpha_(0.1, 0.3, 0.1, 0.6).set()
             else:
                 NSColor.colorWithCalibratedRed_green_blue_alpha_(0.90, 0.97, 0.92, 1.0).set()
             NSBezierPath.fillRect_(band_rect)

        y_limit_high = get_y(250) if not is_mmol else get_y(13.9)
        
        limit_path = NSBezierPath.bezierPath()
        limit_path.setLineWidth_(1.0)
        limit_path.setLineDash_count_phase_([6.0, 4.0], 2, 0.0)
        
        limit_path.moveToPoint_((margin_left, y_low))
        limit_path.lineToPoint_((width - margin_right, y_low))
        
        limit_path.moveToPoint_((margin_left, y_limit_high))
        limit_path.lineToPoint_((width - margin_right, y_limit_high))
        
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.8, 0.3, 0.3, 0.8).set()
        limit_path.stroke()

        grid_path = NSBezierPath.bezierPath()
        grid_path.setLineWidth_(0.5)
        grid_path.setLineDash_count_phase_([2.0, 2.0], 2, 0.0)
        
        axis_font = NSFont.systemFontOfSize_(10)
        if is_dark:
            text_color = NSColor.colorWithCalibratedWhite_alpha_(0.8, 1.0)  
        else:
            text_color = NSColor.colorWithCalibratedWhite_alpha_(0.3, 1.0)  
        
        axis_attrs = {
            NSFontAttributeName: axis_font, 
            NSForegroundColorAttributeName: text_color
        }
        p_style = NSMutableParagraphStyle.alloc().init()
        p_style.setAlignment_(2) 
        y_label_attrs = {
            NSFontAttributeName: axis_font, 
            NSForegroundColorAttributeName: text_color,
            NSParagraphStyleAttributeName: p_style
        }

        for val in grid_values:
            y = get_y(val)
            if y >= margin_bottom and y <= height - margin_top:
                grid_path.moveToPoint_((margin_left, y))
                grid_path.lineToPoint_((width - margin_right, y))
                
                l_str = str(val)
                s = NSString.stringWithString_(l_str).sizeWithAttributes_(y_label_attrs)
                r = NSMakeRect(0, y - s.height/2 + 3, margin_left - 5, s.height)
                NSString.stringWithString_(l_str).drawInRect_withAttributes_(r, y_label_attrs)
                
        if is_dark:
            NSColor.colorWithCalibratedWhite_alpha_(0.35, 1.0).set()  
        else:
            NSColor.colorWithCalibratedWhite_alpha_(0.85, 1.0).set()  
        grid_path.stroke()

        
        if not self.data_points: return
        
        points_coords = []
        count = len(self.data_points)

        
        for i in range(count):
            val, ts = self.data_points[i]
            disp_val = val / factor
            x = get_x(i, count)
            y = get_y(disp_val)
            points_coords.append((x, y, disp_val, ts, val))

        line_path = NSBezierPath.bezierPath()
        for i, (x, y, _, _, _) in enumerate(points_coords):
            if i == 0: line_path.moveToPoint_((x, y))
            else: line_path.lineToPoint_((x, y))
            
        if is_dark:
            NSColor.whiteColor().set()
        else:
            NSColor.blackColor().set()
        line_path.setLineWidth_(2.5)
        line_path.setLineCapStyle_(1) 
        line_path.setLineJoinStyle_(1) 
        line_path.stroke()
        
        hour_dots = []
        
        try:
            import datetime as dt_module
            
            def parse_ts(t_str):
                return dt_module.datetime.strptime(t_str, "%m/%d/%Y %I:%M:%S %p")

            if points_coords:
                last_point = points_coords[-1]
                hour_dots.append(last_point)
                
                last_dot_time = parse_ts(last_point[3])
                
                for i in range(len(points_coords) - 2, -1, -1):
                    p = points_coords[i]
                    p_time = parse_ts(p[3])
                    
                    diff = (last_dot_time - p_time).total_seconds()
                    
                    if diff >= 3300: 
                        hour_dots.append(p)
                        last_dot_time = p_time

        except Exception as e:
            print(f"Error calculating dots: {e}")
            for i, (x, y, _, _, raw_val) in enumerate(points_coords):
                if i % 5 == 0 or i == len(points_coords) - 1:
                    hour_dots.append((x, y, raw_val))
        
        dot_radius = 5.0
        for p in hour_dots:
            if len(p) == 5:
                x, y, _, _, raw_val = p
            else:
                x, y, raw_val = p
                
            dot_rect = NSMakeRect(x - dot_radius, y - dot_radius, dot_radius * 2, dot_radius * 2)
            dot_path = NSBezierPath.bezierPathWithOvalInRect_(dot_rect)
            
            dot_color = self.get_color(raw_val)
            dot_color.set()
            dot_path.fill()
            
            if is_dark:
                NSColor.whiteColor().set()
            else:
                NSColor.blackColor().set()
            dot_path.setLineWidth_(2.0)
            dot_path.stroke()

        clean_coords = []
        for p in points_coords:
            clean_coords.append((p[0], p[1], p[2], p[3]))
        self.points_coords = clean_coords

        indices = [0, count//2, count-1]
        for idx in indices:
            if idx < count:
                x = points_coords[idx][0]
                ts = points_coords[idx][3]
                try:
                    import datetime
                    dt = datetime.datetime.strptime(ts, "%m/%d/%Y %I:%M:%S %p")
                    t_lbl = dt.strftime("%H")
                    s = NSString.stringWithString_(t_lbl).sizeWithAttributes_(axis_attrs)
                    r = NSMakeRect(x - s.width/2, margin_bottom - 28, s.width, s.height)
                    NSString.stringWithString_(t_lbl).drawInRect_withAttributes_(r, axis_attrs)
                    
                    tick = NSBezierPath.bezierPath()
                    tick.moveToPoint_((x, margin_bottom))
                    tick.lineToPoint_((x, margin_bottom - 3))
                    tick.setLineWidth_(1.0)
                    tick.stroke()
                except: pass
                
        
        box_area_height = 34 
        box_y = 5 
        
        
        b_margin_left = margin_left + 40
        b_margin_right = margin_right + 40 
        
        avail_width = width - b_margin_left - b_margin_right
        gap = 25 
        box_width = (avail_width - (2 * gap)) / 3
        
        categories = [
            
            ("High", self.stats.get("high", 0), 
             NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.6, 0.2, 0.15) if is_dark else NSColor.orangeColor().colorWithAlphaComponent_(0.1),
             NSColor.orangeColor()),
             
            ("In Range", self.stats.get("in_range", 0),
             NSColor.greenColor().colorWithAlphaComponent_(0.15),
             NSColor.greenColor() if is_dark else NSColor.colorWithCalibratedRed_green_blue_alpha_(0.0, 0.45, 0.0, 1.0)),
             
            ("Low", self.stats.get("low", 0),
             NSColor.redColor().colorWithAlphaComponent_(0.15),
             NSColor.redColor())
        ]
        
        box_font = NSFont.boldSystemFontOfSize_(11)
        lbl_font = NSFont.systemFontOfSize_(9)
        
        for i, (label, pct, bg_col, text_col) in enumerate(categories):
            bx = b_margin_left + i * (box_width + gap)
            b_rect = NSMakeRect(bx, box_y, box_width, box_area_height)
            
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b_rect, 6, 6)
            bg_col.set()
            path.fill()
            
            
            pct_str = f"{pct}%"
            
            pct_attrs = {
                NSFontAttributeName: box_font,
                NSForegroundColorAttributeName: text_col if not is_dark else text_col.colorWithAlphaComponent_(0.9)
            }
            
            s_pct = NSString.stringWithString_(pct_str).sizeWithAttributes_(pct_attrs)
            
            r_pct = NSMakeRect(
                bx + (box_width - s_pct.width)/2, 
                box_y + 19, 
                s_pct.width, 
                s_pct.height
            )
            NSString.stringWithString_(pct_str).drawInRect_withAttributes_(r_pct, pct_attrs)
            
            lbl_col = NSColor.colorWithCalibratedWhite_alpha_(0.7, 1.0) if is_dark else NSColor.grayColor()
            
            lbl_attrs = {
                NSFontAttributeName: lbl_font,
                NSForegroundColorAttributeName: lbl_col
            }
            s_lbl = NSString.stringWithString_(label).sizeWithAttributes_(lbl_attrs)
            
            r_lbl = NSMakeRect(
                bx + (box_width - s_lbl.width)/2,
                box_y + 4, 
                s_lbl.width,
                s_lbl.height
            )
            NSString.stringWithString_(label).drawInRect_withAttributes_(r_lbl, lbl_attrs)


        if self.hover_point:
             hx, hy = self.hover_point
             NSColor.labelColor().set()
             path = NSBezierPath.bezierPathWithRect_(NSMakeRect(hx-0.5, margin_bottom, 1, plot_height))
             path.fill()

    def mouseMoved_(self, event):
        if not hasattr(self, 'points_coords') or not self.points_coords:
            if hasattr(self, 'tooltip_container'):
                self.tooltip_container.setHidden_(True)
            return
            
        loc = self.convertPoint_fromView_(event.locationInWindow(), None)
        x_mouse = loc.x
        
        is_dark = self.is_dark_mode()
        
        closest = None
        min_dist = 9999
        
        for px, py, val, ts in self.points_coords:
            dist = abs(px - x_mouse)
            if dist < min_dist:
                min_dist = dist
                closest = (px, py, val, ts)
        
        margin_bottom = 60 
        
        if closest and min_dist < 20: 
            px, py, val, ts = closest
            
            unit = getattr(self, 'unit', 'mg/dL')
            if unit == 'mmol/L':
                val_str = f"{val:.1f}"
            else:
                val_str = str(int(val))

            formatted_date = str(ts)
            try:
                from datetime import datetime, timedelta
                dt_obj = datetime.strptime(ts, "%m/%d/%Y %I:%M:%S %p")
                now = datetime.now()
                if dt_obj.date() == now.date():
                    date_str = dt_obj.strftime("%H:%M")
                elif dt_obj.date() == (now.date() - timedelta(days=1)):
                    day_str = "Yesterday"
                    time_str = dt_obj.strftime("%H:%M")
                    date_str = f"{day_str} • {time_str}"
                else:
                    day_str = dt_obj.strftime("%b %d")
                    time_str = dt_obj.strftime("%H:%M")
                    date_str = f"{day_str} • {time_str}"
            except:
                date_str = ts

            full_str = f"{val_str} {unit}\n{date_str}"
            attr_str = NSMutableAttributedString.alloc().initWithString_(full_str)
            
            p_style = NSMutableParagraphStyle.alloc().init()
            p_style.setAlignment_(1) 
            p_style.setLineSpacing_(2)
            
            full_len = len(full_str)
            attr_str.addAttribute_value_range_(NSParagraphStyleAttributeName, p_style, (0, full_len))

            val_only_len = len(val_str)
            val_font = NSFont.boldSystemFontOfSize_(16.0)
            
            if is_dark:
                 val_color = NSColor.whiteColor()
            else:
                 val_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.0, 0.25, 0.36, 1.0) 
            
            attr_str.addAttribute_value_range_(NSFontAttributeName, val_font, (0, val_only_len))
            attr_str.addAttribute_value_range_(NSForegroundColorAttributeName, val_color, (0, val_only_len))
            
            unit_start = val_only_len
            unit_len = len(unit) + 1 
            unit_font = NSFont.systemFontOfSize_(14.0)
            attr_str.addAttribute_value_range_(NSFontAttributeName, unit_font, (unit_start, unit_len))
            attr_str.addAttribute_value_range_(NSForegroundColorAttributeName, val_color, (unit_start, unit_len))
            
            date_start = unit_start + unit_len
            date_len = len(full_str) - date_start
            date_font = NSFont.systemFontOfSize_(11.0)
            
            if is_dark:
                grey_color = NSColor.colorWithCalibratedWhite_alpha_(0.8, 1.0) 
            else:
                grey_color = NSColor.grayColor() 
            attr_str.addAttribute_value_range_(NSFontAttributeName, date_font, (date_start, date_len))
            attr_str.addAttribute_value_range_(NSForegroundColorAttributeName, grey_color, (date_start, date_len))
                         
            self.tooltip_label.setAttributedStringValue_(attr_str)
            
            tooltip_width = 105  
            t_x = px + 10 
            
            view_width = self.bounds().size.width
            if t_x + tooltip_width > view_width:
                t_x = view_width - tooltip_width - 5
            
            if t_x < 0: t_x = 0
            
            t_y = py + 10
            if t_y > self.bounds().size.height - 50: t_y = py - 50
            
            self.tooltip_container.setFrameOrigin_((t_x, t_y))
            self.tooltip_container.setFrameSize_((tooltip_width, 50))
            self.tooltip_label.setFrame_(NSMakeRect(0, 5, tooltip_width, 40))
            
            
            if is_dark:
                bg_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.0, 0.1, 0.25, 0.95)
                border_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.3, 0.5, 1.0)
                self.tooltip_label.setTextColor_(NSColor.whiteColor())
            else:
                bg_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.85, 0.91, 0.98, 0.95)
                border_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.75, 0.82, 0.92, 1.0)
                self.tooltip_label.setTextColor_(NSColor.blackColor()) 
                
            self.tooltip_container.layer().setBackgroundColor_(bg_color.CGColor())
            self.tooltip_container.layer().setBorderColor_(border_color.CGColor())
            
            self.tooltip_container.setHidden_(False)
        else:
            self.tooltip_container.setHidden_(True)
            
    def acceptsFirstMouse_(self, event):
        return True

class CustomGraphView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(CustomGraphView, self).initWithFrame_(frame)
        if self:
            self.setWantsLayer_(True)
            self.layer().setBackgroundColor_(NSColor.whiteColor().CGColor())
            
            self.plot_view = GraphPlotView.alloc().initWithFrame_(self.bounds())
            self.plot_view.setAutoresizingMask_(18)
            self.addSubview_(self.plot_view)
            
        return self
        
    def update_data(self, data):
        if hasattr(self, 'plot_view'):
            self.plot_view.update_data(data)
        
    @property
    def unit(self):
        if hasattr(self, 'plot_view'):
            return self.plot_view.unit
        return "mg/dL"
        
    @unit.setter
    def unit(self, val):
        if hasattr(self, 'plot_view'):
            self.plot_view.unit = val
    
    def set_trend(self, trend):
        if hasattr(self, 'plot_view'):
            self.plot_view.set_trend(trend)
        
    def setNeedsDisplay_(self, flag):
        if hasattr(self, 'plot_view'):
             self.plot_view.setNeedsDisplay_(flag)
        objc.super(CustomGraphView, self).setNeedsDisplay_(flag)

    def viewDidMoveToWindow(self):
        if self.window():
            self.window().setBackgroundColor_(NSColor.whiteColor())

class MenuDelegate(NSObject):
    def initWithApp_(self, app):
         self = objc.super(MenuDelegate, self).init()
         self.app = app
         return self

    def menuWillOpen_(self, menu):
        self.app.update_glucose(None)

USE_DUMMY_DATA = False

class GlucoseApp(rumps.App):
    TREND_ARROWS = {
        1: "↓",
        2: "↘",
        3: "→",
        4: "↗",
        5: "↑"
    }

    def __init__(self):
        super(GlucoseApp, self).__init__("Schugaa", icon=None, quit_button=None)
        self.config = self.load_config()
        self.client = LibreClient(
            self.config.get("email"), 
            self.config.get("password"), 
            self.config.get("region", "eu")
        )
        self.menu = []
        self.quit_button = None
        
        self.last_sensor_activated = None
        
        self.menu_handler = MenuActionHandler.alloc().initWithApp_(self)

        self.setup_application_menu()

        self.graph_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        self.graph_view = CustomGraphView.alloc().initWithFrame_(NSMakeRect(0, 0, 450, 300))
        self.graph_view.unit = self.config.get("unit", "mg/dL")
        self.graph_item.setView_(self.graph_view)
        
        self.menu.clear() 
        
        
        self._menu._menu.addItem_(self.graph_item)
        
        try:
            is_dark = NSUserDefaults.standardUserDefaults().stringForKey_("AppleInterfaceStyle") == "Dark"
            if not is_dark:
                self._menu._menu.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameAqua"))
            else:
                self._menu._menu.setAppearance_(None)
        except:
            pass
        
        self.status_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        self.status_menu_item.setEnabled_(False)
        
        status_view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 450, 22))
        status_view.setWantsLayer_(True)
        cream_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.992, 0.816, 1.0)
        status_view.layer().setBackgroundColor_(cream_color.CGColor())
        
        label_y = 2
        label_height = 18
        font_size = 13.0
        text_color = NSColor.colorWithCalibratedWhite_alpha_(0.2, 1.0)
        font = NSFont.systemFontOfSize_(font_size)
        
        self.status_label = NSTextField.alloc().initWithFrame_(NSMakeRect(10, label_y, 130, label_height))
        self.status_label.setBezeled_(False)
        self.status_label.setDrawsBackground_(False)
        self.status_label.setEditable_(False)
        self.status_label.setSelectable_(False)
        self.status_label.setAlignment_(0) 
        self.status_label.setStringValue_("Status: OK")
        self.status_label.setFont_(font)
        self.status_label.setTextColor_(text_color)
        status_view.addSubview_(self.status_label)
        
        self.last_update_label = NSTextField.alloc().initWithFrame_(NSMakeRect(140, label_y, 170, label_height))
        self.last_update_label.setBezeled_(False)
        self.last_update_label.setDrawsBackground_(False)
        self.last_update_label.setEditable_(False)
        self.last_update_label.setSelectable_(False)
        self.last_update_label.setAlignment_(1) 
        self.last_update_label.setStringValue_("Last updated: --")
        self.last_update_label.setFont_(font)
        self.last_update_label.setTextColor_(text_color)
        status_view.addSubview_(self.last_update_label)
        
        self.sensor_label = NSTextField.alloc().initWithFrame_(NSMakeRect(310, label_y, 130, label_height))
        self.sensor_label.setBezeled_(False)
        self.sensor_label.setDrawsBackground_(False)
        self.sensor_label.setEditable_(False)
        self.sensor_label.setSelectable_(False)
        self.sensor_label.setAlignment_(2) 
        self.sensor_label.setStringValue_("Sensor: --")
        self.sensor_label.setFont_(font)
        self.sensor_label.setTextColor_(text_color)
        status_view.addSubview_(self.sensor_label)
        
        self.status_menu_item.setView_(status_view)
        self._menu._menu.addItem_(self.status_menu_item)
        
        self.menu_delegate = MenuDelegate.alloc().initWithApp_(self)
        self._menu._menu.setDelegate_(self.menu_delegate)
        
        # Setup Theme Observer
        self.theme_observer = ThemeChangeObserver.alloc().initWithApp_(self)
        try:
             from Foundation import NSDistributedNotificationCenter
             NSDistributedNotificationCenter.defaultCenter().addObserver_selector_name_object_(
                 self.theme_observer,
                 "themeChanged:",
                 "AppleInterfaceThemeChangedNotification",
                 None
             )
        except Exception as e:
             print(f"Failed to register theme observer: {e}")

        self.data_queue = queue.Queue()
        self.update_status_bar_appearance()
        self.update_glucose(None)
        



    def setup_application_menu(self):
        try:
            main_menu = NSMenu.alloc().init()
            app_menu_item = NSMenuItem.alloc().init()
            app_menu_item.setTitle_("Schugaa")
            main_menu.addItem_(app_menu_item)
            
            app_menu = NSMenu.alloc().initWithTitle_("Schugaa")
            app_menu_item.setSubmenu_(app_menu)
            
            units_item = NSMenuItem.alloc().init()
            units_item.setTitle_("Units")
            app_menu.addItem_(units_item)
            
            units_menu = NSMenu.alloc().initWithTitle_("Units")
            units_item.setSubmenu_(units_menu)
            
            mgdl_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("mg/dL", "setUnitMgdl:", "")
            mgdl_item.setTarget_(self.menu_handler)
            units_menu.addItem_(mgdl_item)
            
            mmol_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("mmol/L", "setUnitMmol:", "")
            mmol_item.setTarget_(self.menu_handler)
            units_menu.addItem_(mmol_item)
            
            app_menu.addItem_(NSMenuItem.separatorItem())

            refresh_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Refresh Now", "refresh:", "r")
            refresh_item.setTarget_(self.menu_handler)
            app_menu.addItem_(refresh_item)
            
            logout_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Logout", "logout:", "")
            logout_item.setTarget_(self.menu_handler)
            app_menu.addItem_(logout_item)
            
            app_menu.addItem_(NSMenuItem.separatorItem())

            donate_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Donate", "donate:", "")
            donate_item.setTarget_(self.menu_handler)
            app_menu.addItem_(donate_item)
            
            debug_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Share Debug Logs", "shareDebugLogs:", "")
            debug_item.setTarget_(self.menu_handler)
            app_menu.addItem_(debug_item)
            
            app_menu.addItem_(NSMenuItem.separatorItem())
            
            quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit Schugaa", "quit:", "q")
            quit_item.setTarget_(self.menu_handler)
            app_menu.addItem_(quit_item)
            
            NSApplication.sharedApplication().setMainMenu_(main_menu)
        except Exception as e:
            print(f"Failed to setup menu: {e}")

    def set_unit(self, unit):
        self.config["unit"] = unit
        write_json_secure(get_config_path(), self.config)
        
        if hasattr(self, 'graph_view'):
            self.graph_view.unit = unit
            self.graph_view.setNeedsDisplay_(True)
            
        self.update_glucose(None)

    def logout(self, sender):
        config_path = get_config_path()
        if os.path.exists(config_path):
            try:
                if self.config and self.config.get("email"):
                    delete_keyring_password(self.config.get("email"))
                os.remove(config_path)
                rumps.alert("Logged Out", "Your credentials have been removed. The application will now quit.")
                rumps.quit_application()
            except Exception as e:
                rumps.alert("Error", f"Failed to remove credentials: {e}")
        else:
             rumps.alert("Info", "No credentials found to remove.")
             rumps.quit_application()

    def load_config(self):
        config = load_config_data()
        if not config:
            return {}
            
        try:
            if "email" in config:
                try:
                    import base64
                    config["email"] = base64.b64decode(config["email"]).decode('utf-8')
                except:
                    pass 

            if "password" in config:
                try:
                    import base64
                    config["password"] = base64.b64decode(config["password"]).decode('utf-8')
                except:
                    pass
            if not config.get("password") or config.get("password") == "__keyring__":
                kr_pw = get_keyring_password(config.get("email"))
                if kr_pw:
                    config["password"] = kr_pw

            return config
        except Exception as e:
            rumps.alert("Error", f"Could not process config: {e}")
            return {}

    @rumps.timer(60)
    def update_timer(self, sender):
        self.update_glucose(sender)
        
    @rumps.timer(1)
    def ui_update_loop(self, sender):
        try:
            while not self.data_queue.empty():
                data = self.data_queue.get_nowait()
                self._update_ui_with_data(data)
        except queue.Empty:
            pass

    def refresh_now(self, sender):
        self.update_glucose(sender, force=True)

    def update_glucose(self, sender, force=False):
        now = time.time()
        last = getattr(self, 'last_fetch_time', 0)
        if not force and now - last < 45:
            print(f"Skipping update (Debounce: {int(45 - (now - last))}s remaining)")
            return
        if force and now - last < 10:
            print(f"Skipping update (Force Debounce: {int(10 - (now - last))}s remaining)")
            return
             
        self.last_fetch_time = now
        
        thread = threading.Thread(target=self._fetch_and_update, daemon=True)
        thread.start()


    def _fetch_and_update(self):
        try:
            if USE_DUMMY_DATA:
                print("Generating dummy data...")
                data = self.generate_dummy_data()
                time.sleep(0.5)
            else:
                if not self.client:
                   self.client = LibreClient(
                       self.config.get("email"),
                       self.config.get("password"),
                       self.config.get("region", "eu")
                   )
                
                print("Fetching glucose data...")
                data = self.client.get_latest_glucose(retry=True)

            if data:
                self.data_queue.put(data)
            else:
                if self.client and getattr(self.client, "last_error", None):
                    err = self.client.last_error
                    self.data_queue.put({"Error": err.get("type"), "Message": err.get("message")})
                else:
                    self.data_queue.put(None)
                
        except Exception as e:
            print(f"Error fetching glucose: {e}")
            self.data_queue.put(None)



    def generate_dummy_data(self):
        import math
        import random
        from datetime import datetime, timedelta
        
        now = datetime.now()
        base_glucose = 120
        amplitude = 40
        period_minutes = 120 
        
        minutes = now.hour * 60 + now.minute
        val = base_glucose + amplitude * math.sin(2 * math.pi * minutes / period_minutes)
        val += random.uniform(-5, 5)
        
        next_minutes = minutes + 5
        next_val = base_glucose + amplitude * math.sin(2 * math.pi * next_minutes / period_minutes)
        diff = next_val - val
        
        if diff > 2: trend = 5 
        elif diff > 1: trend = 4 
        elif diff < -2: trend = 1 
        elif diff < -1: trend = 2 
        else: trend = 3 
        
        color = 1 
        if val > 180 or val < 70: color = 2 
        if val > 240 or val < 54: color = 3 
        
        history = []
        for i in range(50): 
            t_offset = i * 5
            hist_time = now - timedelta(minutes=t_offset)
            h_mins = hist_time.hour * 60 + hist_time.minute
            
            h_val = base_glucose + amplitude * math.sin(2 * math.pi * h_mins / period_minutes)
            h_val += random.uniform(-3, 3)
            
            ts_str = hist_time.strftime("%-m/%-d/%Y %-I:%M:%S %p")
            
            history.append({
                'Value': h_val,
                'Timestamp': ts_str
            })
        
        history.reverse() 
        
        sensor_activated = int(time.time()) - (30 * 60)  
        sensor_expires = sensor_activated + (14 * 24 * 60 * 60)  
        
        
        return {
            'Value': val,
            'Trend': trend,
            'TrendArrow': trend, 
            'Color': color,
            'GraphData': history,
            'Unit': self.config.get("unit", "mg/dL"),
            'SensorActivated': sensor_activated,
            'SensorExpires': sensor_expires
        }
            
    def _update_ui_with_data(self, data):
        try:
            if not data:
                if self.title and "Created" not in self.title and "???" not in self.title:
                    return
                self.title = "???"
                return

            value = data.get("Value")
            if value is None:
                if data.get("Error") == "rate_limit":
                    self.title = "Rate limited"
                    if hasattr(self, "status_label"):
                        self.status_label.setStringValue_("Status: Rate limited")
                        if hasattr(self, "last_update_label"):
                            if hasattr(self, "last_updated_at"):
                                self.last_update_label.setStringValue_(f"Last updated: {self.last_updated_at.strftime('%H:%M')}")
                            else:
                                self.last_update_label.setStringValue_("Last updated: --")
                        if hasattr(self, "sensor_label"):
                            self.sensor_label.setStringValue_("Sensor: --")
                    return
                if self.title and "Created" not in self.title and "???" not in self.title:
                    return
                self.title = "???"
                return
                
            sensor_activated = data.get("SensorActivated")
            if sensor_activated:
                self.last_sensor_activated = sensor_activated
                
            graph_data = data.get("GraphData", [])
            
            # Filter out data points from before current sensor activation
            if sensor_activated and graph_data:
                from datetime import datetime
                filtered_data = []
                for point in graph_data:
                    ts_str = point.get("Timestamp")
                    if ts_str:
                        try:
                            dt = datetime.strptime(ts_str, "%m/%d/%Y %I:%M:%S %p")
                            if dt.timestamp() >= sensor_activated:
                                filtered_data.append(point)
                        except Exception:
                            pass
                graph_data = filtered_data
                
            # If no valid data for current sensor, show waiting status
            if not graph_data and sensor_activated:
                if hasattr(self, "status_label"):
                    self.status_label.setStringValue_("Status: Waiting for data")
                    from AppKit import NSColor
                    self.status_label.setTextColor_(NSColor.orangeColor())
                if hasattr(self, 'graph_view'):
                    self.graph_view.update_data([])
                self.title = "..."
                return

            if hasattr(self, 'graph_view'):
                self.graph_view.update_data(graph_data)
                
            trend = data.get("TrendArrow")
            if hasattr(self, 'graph_view'):
                self.graph_view.set_trend(trend)
                
            self.update_status_bar_appearance()

            arrow = self.TREND_ARROWS.get(trend, "")
            
            unit = self.config.get("unit", "mg/dL")
            disp_val = to_display_value(value, unit)
            val_str = f"{disp_val:.1f}" if unit == "mmol/L" else str(int(disp_val))
            
            title_str = f" {val_str} {arrow} "
            
            text_color = None
            
            try:
                from AppKit import NSColor, NSFont, NSFontAttributeName, NSForegroundColorAttributeName, NSAttributedString, NSString, NSStatusItem
                
                if value < 70:
                    text_color = NSColor.redColor()
                elif 70 <= value <= 79:
                    text_color = NSColor.yellowColor()
                elif 80 <= value <= 180:
                    text_color = NSColor.greenColor()
                elif 181 <= value <= 220:
                    text_color = NSColor.yellowColor()
                elif 221 <= value <= 250:
                    text_color = NSColor.orangeColor()
                else: 
                    text_color = NSColor.redColor()

            except Exception:
                self.title = title_str
                return
                
            attrs = {
                NSForegroundColorAttributeName: text_color,
                NSFontAttributeName: NSFont.boldSystemFontOfSize_(14.0) 
            }
            ns_title = NSString.stringWithString_(title_str)
            attr_str = NSAttributedString.alloc().initWithString_attributes_(ns_title, attrs)
            
            status_item = None
            if hasattr(self, '_nsapp') and hasattr(self._nsapp, 'nsstatusitem'):
                status_item = self._nsapp.nsstatusitem
            
            if not status_item and hasattr(self, '_nsstatusitem'):
                status_item = self._nsstatusitem
            elif hasattr(self, '_status_item'):
                status_item = self._status_item
            
            if not status_item:
                 try:
                     if hasattr(self, '_application_support'):
                        status_item = self._application_support.nsstatusitem
                 except:
                     pass
            
            if not status_item:
                 try:
                     if hasattr(self, '_application_support'):
                        pass
                 except:
                     pass
                     
                 for k, v in self.__dict__.items():
                     if "statusitem" in str(k).lower() and hasattr(v, 'button'):
                         status_item = v
                         break
            
            if status_item:
                status_item.button().setAttributedTitle_(attr_str)
            else:
                 self.title = title_str

            try:
                from datetime import datetime, timedelta
                self.last_updated_at = datetime.now()
                
                # Check for connection status from API (2 = Disconnected/Signal Loss)
                # But prioritize showing OK if we have valid data
                conn_status = data.get("ConnectionStatus")
                has_valid_data = (value is not None and graph_data)
                is_signal_loss = (conn_status == 2 and not has_valid_data)

                if hasattr(self, "status_label"):
                    if is_signal_loss:
                         self.status_label.setStringValue_("Status: Signal Loss")
                         self.status_label.setTextColor_(NSColor.redColor())
                    else:
                         self.status_label.setStringValue_("Status: OK")
                         is_dark = self.is_dark_mode()
                         if is_dark:
                            self.status_label.setTextColor_(NSColor.whiteColor())
                         else:
                            self.status_label.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.2, 1.0))



                    sensor_text = "--"
                    sensor_activated = data.get("SensorActivated")
                    sensor_expires = data.get("SensorExpires")
                    
                    if sensor_activated:
                        now_ts = time.time()
                        warmup_duration = 60 * 60  
                        warmup_end = sensor_activated + warmup_duration
                        
                        if now_ts < warmup_end:
                            minutes_remaining = int((warmup_end - now_ts) / 60)
                            if minutes_remaining == 0:
                                sensor_text = "Warming up (<1 min)"
                            elif minutes_remaining == 1:
                                sensor_text = "Warming up (1 min)"
                            else:
                                sensor_text = f"Warming up ({minutes_remaining} min)"
                        elif sensor_expires:
                            remaining_seconds = sensor_expires - now_ts
                            days_remaining = remaining_seconds / (24 * 60 * 60)
                            
                            if days_remaining > 0:
                                if days_remaining < 1:
                                    hours_int = max(1, math.ceil(remaining_seconds / (60 * 60)))
                                    if hours_int == 1:
                                        sensor_text = "1 hour"
                                    else:
                                        sensor_text = f"{hours_int} hours"
                                else:
                                    days_int = math.ceil(days_remaining)
                                    if days_int == 1:
                                        sensor_text = "1 day"
                                    else:
                                        sensor_text = f"{days_int} days"
                            else:
                                sensor_text = "Expired ⚠️"
                    elif sensor_expires:
                        now_ts = time.time()
                        remaining_seconds = sensor_expires - now_ts
                        days_remaining = remaining_seconds / (24 * 60 * 60)
                        
                        if days_remaining > 0:
                            if days_remaining < 1:
                                hours_int = max(1, math.ceil(remaining_seconds / (60 * 60)))
                                if hours_int == 1:
                                    sensor_text = "1 hour"
                                else:
                                    sensor_text = f"{hours_int} hours"
                            else:
                                days_int = math.ceil(days_remaining)
                                if days_int == 1:
                                    sensor_text = "1 day"
                                else:
                                    sensor_text = f"{days_int} days"
                        else:
                            sensor_text = "Expired ⚠️"

                    if hasattr(self, "last_update_label"):
                        self.last_update_label.setStringValue_(f"Last updated: {self.last_updated_at.strftime('%H:%M')}")
                    if hasattr(self, "sensor_label"):
                        self.sensor_label.setStringValue_(f"Sensor: {sensor_text}")


            except Exception:
                pass

                 
        except Exception as e:
            pass
            self.title = "Err"

    def is_dark_mode(self):
        """Check if system is in dark mode using effectiveAppearance"""
        try:
            # First try to get appearance from the menu's view if possible, essentially "app appearance"
            if hasattr(self, 'status_menu_item'):
                view = self.status_menu_item.view()
                if view:
                     appearance = view.effectiveAppearance()
                     if appearance:
                         return "Dark" in appearance.name()
            
            # Fallback to NSApp
            if hasattr(NSApplication, 'sharedApplication'):
                app = NSApplication.sharedApplication()
                if app:
                     return "Dark" in app.effectiveAppearance().name()
                     
            # Fallback to defaults
            style = NSUserDefaults.standardUserDefaults().stringForKey_("AppleInterfaceStyle")
            return style == "Dark"
        except:
            return False

    def update_status_bar_appearance(self):
        """Update status bar colors based on current system theme"""
        if not hasattr(self, 'status_menu_item'):
            return
            
        # Access the view from the menu item
        status_view = self.status_menu_item.view()
        if not status_view:
            return

        is_dark = self.is_dark_mode()
        
        # Update background color
        if is_dark:
            # Dark mode: Dark gray background
            bg_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.1, 0.1, 0.1, 1.0)
        else:
            # Light mode: Cream background
            bg_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.992, 0.816, 1.0)
            
        status_view.layer().setBackgroundColor_(bg_color.CGColor())
        
        # Update text colors
        if is_dark:
            text_color = NSColor.whiteColor()
        else:
            text_color = NSColor.colorWithCalibratedWhite_alpha_(0.2, 1.0)
            
        if hasattr(self, 'status_label'):
            self.status_label.setTextColor_(text_color)
        if hasattr(self, 'last_update_label'):
            self.last_update_label.setTextColor_(text_color)
        if hasattr(self, 'sensor_label'):
            self.sensor_label.setTextColor_(text_color)

def get_config_path():
    
    home = os.path.expanduser("~")
    app_dir = os.path.join(home, ".schugaa")
    if not os.path.exists(app_dir):
        os.makedirs(app_dir, exist_ok=True)
    return os.path.join(app_dir, "config.json")
    

def setup_logging():
    """ Redirects stdout and stderr to a log file """
    log_dir = os.path.expanduser("~/Library/Logs/Schugaa")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, "schugaa.log")
    try:
        if not os.path.exists(log_file):
            with open(log_file, "a"):
                pass
        os.chmod(log_file, 0o600)
    except Exception:
        pass
    
    class DualWriter:
        def __init__(self, original_stream, file_path):
            self.original_stream = original_stream
            self.file = open(file_path, "a", buffering=1) 
            
        def write(self, message):
            self.original_stream.write(message)
            self.file.write(message)
            
        def flush(self):
            self.original_stream.flush()
            self.file.flush()

    sys.stdout = DualWriter(sys.stdout, log_file)
    sys.stderr = DualWriter(sys.stderr, log_file)
    print(f"--- Log Session Started: {time.ctime()} ---")

def load_config_data():
    config_path = get_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except:
            pass
            
    try:
        with open(resource_path("config.json"), "r") as f:
            return json.load(f)
    except:
        return None


if __name__ == "__main__":
    setup_logging()

    set_dock_icon()
    
    try:
        from Foundation import NSBundle
        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info:
            info['CFBundleName'] = 'Schugaa'
    except Exception as e:
        pass
    

    config = load_config_data()
    
    needs_login = True
    if config and config.get("email"):
        temp_email = config.get("email")
        try:
            import base64
            temp_email = base64.b64decode(temp_email).decode('utf-8')
        except Exception:
            pass
        if config.get("password") or get_keyring_password(temp_email):
            needs_login = False
        
    def perform_login():
        try:
            from AppKit import (NSAlert, NSView, NSTextField, NSSecureTextField, NSPopUpButton, 
                              NSMakeRect, NSStackView, NSUserInterfaceLayoutOrientationVertical,
                              NSLayoutAttributeLeading, NSLayoutAttributeTrailing, NSLayoutAttributeTop,
                              NSLayoutAttributeBottom, NSLayoutAttributeWidth, NSLayoutRelationEqual,
                              NSImage, NSApplication, NSRunningApplication, NSApplicationActivateIgnoringOtherApps) 
            import objc
        except ImportError:
            rumps.alert("Error", "Missing AppKit. Please ensure pyobjc-framework-Cocoa is installed.")
            return False

        alert = NSAlert.alloc().init()
        alert.setMessageText_("Schugaa Login")
        alert.setInformativeText_("Enter your LibreLinkUp credentials.")
        alert.addButtonWithTitle_("Login")
        alert.addButtonWithTitle_("Cancel")
        
        icon_path = resource_path("Schugaa.icns")
        if os.path.exists(icon_path):
             image = NSImage.alloc().initWithContentsOfFile_(icon_path)
             if image:
                 alert.setIcon_(image)

        wrapper_frame = NSMakeRect(0, 0, 300, 120)
        wrapper_view = NSView.alloc().initWithFrame_(wrapper_frame)

        
        region_popup = NSPopUpButton.alloc().initWithFrame_(NSMakeRect(10, 80, 135, 24))
        regions = ['eu', 'us', 'au', 'ca', 'global', 'de', 'fr', 'jp', 'ap', 'ae', 'la', 'eu2', 'gb', 'ru', 'tw', 'kr']
        region_popup.addItemsWithTitles_(regions)
        region_popup.selectItemWithTitle_("eu")
        
        unit_popup = NSPopUpButton.alloc().initWithFrame_(NSMakeRect(155, 80, 135, 24))
        units = ['mg/dL', 'mmol/L']
        unit_popup.addItemsWithTitles_(units)
        unit_popup.selectItemWithTitle_("mg/dL")
        
        email_field = NSTextField.alloc().initWithFrame_(NSMakeRect(10, 50, 280, 24))
        email_field.setPlaceholderString_("LibreLinkUp Email")
        
        pass_field = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(10, 20, 280, 24))
        pass_field.setPlaceholderString_("LibreLinkUp Password")
        
        wrapper_view.addSubview_(region_popup)
        wrapper_view.addSubview_(unit_popup)
        wrapper_view.addSubview_(email_field)
        wrapper_view.addSubview_(pass_field)
        
        alert.setAccessoryView_(wrapper_view)
        
        NSApplication.sharedApplication().setActivationPolicy_(0) 
        NSRunningApplication.currentApplication().activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        
        while True:
            NSRunningApplication.currentApplication().activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            
            response = alert.runModal()
            
            if response == 1000: 
                email = email_field.stringValue().strip()
                password = pass_field.stringValue().strip()
                region = region_popup.selectedItem().title()
                unit = unit_popup.selectedItem().title()
                
                if not email or not password:
                    continue
                
                try:
                    client = LibreClient(email, password, region)
                    if not client.login():
                        rumps.alert("Login Failed", "Could not authenticate with LibreLinkUp. Check credentials or try another region.")
                        continue
                        
                    client.get_latest_glucose()
                    
                    final_region = client.region
                    
                    import base64
                    email_b64 = base64.b64encode(email.encode('utf-8')).decode('utf-8')
                    password_store = "__keyring__" if set_keyring_password(email, password) else None
                    if not password_store:
                        import base64
                        password_store = base64.b64encode(password.encode('utf-8')).decode('utf-8')

                    config = {
                        "email": email_b64,
                        "password": password_store,
                        "region": final_region,
                        "unit": unit
                    }
                    
                    write_json_secure(get_config_path(), config)
                        
                    rumps.alert("Success", "Login successful!")
                    return True
                    
                except Exception as e:
                    rumps.alert("Login Failed", f"Could not verify credentials: {e}")
                    continue
                    
            else:
                return False

    app = NSApplication.sharedApplication()
    app.setAppearance_(None) 
    
    if needs_login:
        if not perform_login():
            sys.exit(0)
            
    GlucoseApp().run()
