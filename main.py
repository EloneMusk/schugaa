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
from Foundation import NSMakeRect, NSURL
import objc

MMOL_FACTOR = 18.0182

def _get_keyring():
    try:
        import keyring  # type: ignore
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
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

from datetime import datetime
import queue

def set_dock_icon():
    # Force set the Dock icon (Application Icon)
    # This is distinct from the Menu Bar icon (Status Item)
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
        log_path = os.path.expanduser("~/Library/Logs/Schugaa/schugaa.log")
        if os.path.exists(log_path):
             NSWorkspace.sharedWorkspace().selectFile_inFileViewerRootedAtPath_(log_path, None)
        else:
             print("Log file not found.")

class GraphPlotView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(GraphPlotView, self).initWithFrame_(frame)
        if self:

            self.data_points = []
            self.hover_point = None
            self.unit = "mg/dL"
            
            # Tracking area for hover
            options = (NSTrackingMouseEnteredAndExited | 
                      NSTrackingMouseMoved | 
                      NSTrackingActiveInKeyWindow | 
                      NSTrackingActiveAlways |
                      NSTrackingInVisibleRect)
            tracking_area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
                self.bounds(), options, self, None)
            self.addTrackingArea_(tracking_area)
            
            # Tooltip Container - Glass Effect (NSVisualEffectView)
            # Use raw integers for Material: 2 = Popover (Light), 0 = HUD (Dark), 8 = ToolTip
            # BlendingMode: 1 = WithinWindow
            self.tooltip_container = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, 130, 45))
            self.tooltip_container.setMaterial_(1) # Light
            self.tooltip_container.setBlendingMode_(1) # WithinWindow
            self.tooltip_container.setState_(1) # Active
            # Force Light Appearance (VibrantLight) to ensure glass look isn't gray/dark
            self.tooltip_container.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameVibrantLight"))
            self.tooltip_container.setWantsLayer_(True)
            self.tooltip_container.layer().setCornerRadius_(12)
            self.tooltip_container.layer().setMasksToBounds_(True)
            self.tooltip_container.setHidden_(True)
            
            # Add shadow to container view (requires not masking bounds for shadow? 
            # NSVisualEffectView clipping makes shadow tricky. 
            # Ideally we wrap VE in a clear view with shadow, OR just rely on VE internal look. 
            # Let's try adding shadow to the VE layer first, but setMasksToBounds might clip it.
            # Let's SKIP shadow on the VE for this pass to ensure the BLUR works, 
            # or wrap it. A simple pill blur is often good enough for "iOS style".
            
            # Tooltip Label (Text Content)
            self.tooltip_label = NSTextField.alloc().initWithFrame_(self.tooltip_container.bounds())
            self.tooltip_label.setBezeled_(False)
            self.tooltip_label.setDrawsBackground_(False)
            self.tooltip_label.setBackgroundColor_(NSColor.clearColor())
            self.tooltip_label.setEditable_(False)
            self.tooltip_label.setSelectable_(False)
            # Autoresize with container
            self.tooltip_label.setAutoresizingMask_(18) # Width+Height resizable
            
            self.tooltip_container.addSubview_(self.tooltip_label)
            self.addSubview_(self.tooltip_container)
            


            self.trend = 3 # Default Stable
            
        return self

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
        else: # > 250
            return NSColor.redColor()

    def set_trend(self, trend):
        self.trend = trend
        self.setNeedsDisplay_(True)

    def update_data(self, data):
        # Data is list of dicts: {'Value': int, 'Timestamp': str}
        self.data_points = []
        try:
            for point in data:
                val = point.get("Value")
                ts = point.get("Timestamp")
                if val:
                    # Store tuple (value, timestamp)
                    self.data_points.append((val, ts))
            
            # Limit to plausible amount to fit graph
            if len(self.data_points) > 100:
                 self.data_points = self.data_points[-100:]
                 
        except Exception as e:
            print(f"Error parsing graph data: {e}")
            
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        if not self.data_points:
             return

        # 1. Solid White Background - Fill bounds to cover everything
        NSColor.whiteColor().set()
        NSBezierPath.fillRect_(self.bounds())
        
        width = rect.size.width
        height = rect.size.height
        
        # Dimensions & Scaling
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
            # User request: Reduce gap above 300
            max_y_val = 300 
            min_y_val = 50 
            grid_values = [50, 100, 150, 200, 250, 300]
            val_70 = 70
            val_180 = 180

        y_range = max_y_val - min_y_val
        
        # Margins (Optimized)
        margin_left = 45 # Increased padding on left
        margin_right = 20
        # Reduced margins safely to remove unused space
        margin_top = 20 
        margin_bottom = 25 # Reduced padding from bottom
        
        plot_width = width - margin_left - margin_right
        plot_height = height - margin_bottom - margin_top
        
        def get_y(val):
            val_clamped = max(min(val, max_y_val), min_y_val)
            normalized = (val_clamped - min_y_val) / y_range
            return margin_bottom + normalized * plot_height

        def get_x(index, total):
            step = plot_width / max(total - 1, 1) if total > 1 else 0
            return margin_left + index * step

        # --- 2. Target Range (Light Green Band) ---
        y_low = get_y(val_70)
        y_high = get_y(val_180)
        
        if y_high > y_low:
             band_rect = NSMakeRect(margin_left, y_low, plot_width, y_high - y_low)
             # Very Light Green #e6f7eb approx
             NSColor.colorWithCalibratedRed_green_blue_alpha_(0.90, 0.97, 0.92, 1.0).set()
             NSBezierPath.fillRect_(band_rect)

        # --- 3. Dashed Limit Lines (Low/High) ---
        # User requested dotted line at 250
        y_limit_high = get_y(250) if not is_mmol else get_y(13.9)
        
        limit_path = NSBezierPath.bezierPath()
        limit_path.setLineWidth_(1.0)
        limit_path.setLineDash_count_phase_([6.0, 4.0], 2, 0.0)
        
        # Low Limit (70)
        limit_path.moveToPoint_((margin_left, y_low))
        limit_path.lineToPoint_((width - margin_right, y_low))
        
        # High Limit (250)
        limit_path.moveToPoint_((margin_left, y_limit_high))
        limit_path.lineToPoint_((width - margin_right, y_limit_high))
        
        # Red-ish color for limits
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.8, 0.3, 0.3, 0.8).set()
        limit_path.stroke()

        # --- 4. Grid Lines (Faint Grey) ---
        grid_path = NSBezierPath.bezierPath()
        grid_path.setLineWidth_(0.5)
        grid_path.setLineDash_count_phase_([2.0, 2.0], 2, 0.0)
        
        axis_font = NSFont.systemFontOfSize_(10)
        # Using dark grey for text
        text_color = NSColor.colorWithCalibratedWhite_alpha_(0.3, 1.0) 
        
        axis_attrs = {
            NSFontAttributeName: axis_font, 
            NSForegroundColorAttributeName: text_color
        }
        p_style = NSMutableParagraphStyle.alloc().init()
        p_style.setAlignment_(2) # Right
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
                # Shifted up slightly (+3) to be "upside"
                r = NSMakeRect(0, y - s.height/2 + 3, margin_left - 5, s.height)
                NSString.stringWithString_(l_str).drawInRect_withAttributes_(r, y_label_attrs)
                
        NSColor.colorWithCalibratedWhite_alpha_(0.85, 1.0).set() # Faint grey grid
        grid_path.stroke()

        # --- 5. Axes Vertical Line (Divider) ---
        # Drawing a solid vertical line at the right end of the plot (optional, like reference image?)
        # Reference has a vertical line indicating "Now" or current time. 
        # We can just draw axes as usual or minimal.
        
        # --- 6. Data Plot ---
        if len(self.data_points) < 2: return
        
        points_coords = []
        count = len(self.data_points)
        
        for i in range(count):
            val, ts = self.data_points[i]
            disp_val = val / factor
            x = get_x(i, count)
            y = get_y(disp_val)
            points_coords.append((x, y, disp_val, ts, val))

        # A. Connection Line (Solid Dark Blue)
        line_path = NSBezierPath.bezierPath()
        for i, (x, y, _, _, _) in enumerate(points_coords):
            if i == 0: line_path.moveToPoint_((x, y))
            else: line_path.lineToPoint_((x, y))
            
        # Dark Blue #003f5c
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.0, 0.25, 0.36, 1.0).set()
        line_path.setLineWidth_(3.0)
        line_path.setLineCapStyle_(1) # Round
        line_path.setLineJoinStyle_(1) # Round
        line_path.stroke()
        
        # B. End Dot? (Reference shows end dot? No, reference doesn't show clearer dots on line, maybe end one)
        # User said "show only line". So NO dots.

        # Draw Trend Dot at the last point
        last_x, last_y, _, _, last_val = points_coords[-1]
        
        dot_path = NSBezierPath.bezierPath()
        dot_radius = 4.0
        dot_rect = NSMakeRect(last_x - dot_radius, last_y - dot_radius, dot_radius * 2, dot_radius * 2)
        dot_path.appendBezierPathWithOvalInRect_(dot_rect)
        
        # Trend Color
        # User requested "color as per blood sugar values".
        # So we use get_color(value) for the dot.
        dot_color = self.get_color(last_val)
             
        dot_color.set()
        dot_path.fill()

        # Save coords for hover
        clean_coords = []
        for p in points_coords:
            clean_coords.append((p[0], p[1], p[2], p[3]))
        self.points_coords = clean_coords

        # X-Axis Labels (Time)
        # Label start, middle, end
        indices = [0, count//2, count-1]
        for idx in indices:
            if idx < count:
                x = points_coords[idx][0]
                ts = points_coords[idx][3]
                try:
                    import datetime
                    dt = datetime.datetime.strptime(ts, "%m/%d/%Y %I:%M:%S %p")
                    # HH
                    t_lbl = dt.strftime("%H")
                    s = NSString.stringWithString_(t_lbl).sizeWithAttributes_(axis_attrs)
                    # Shifted down slightly - using margin_bottom-25
                    r = NSMakeRect(x - s.width/2, margin_bottom - 25, s.width, s.height)
                    NSString.stringWithString_(t_lbl).drawInRect_withAttributes_(r, axis_attrs)
                    
                    # Tick mark
                    tick = NSBezierPath.bezierPath()
                    tick.moveToPoint_((x, margin_bottom))
                    tick.lineToPoint_((x, margin_bottom - 3))
                    tick.setLineWidth_(1.0)
                    tick.stroke()
                except: pass
                
        # Hover Line
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
        
        # Find closest point
        closest = None
        min_dist = 9999
        
        for px, py, val, ts in self.points_coords:
            dist = abs(px - x_mouse)
            if dist < min_dist:
                min_dist = dist
                closest = (px, py, val, ts)
                
        if closest and min_dist < 20: # Snap distance
            px, py, val, ts = closest
            
            # Formatting Value
            unit = getattr(self, 'unit', 'mg/dL')
            if unit == 'mmol/L':
                val_str = f"{val:.1f}"
            else:
                val_str = str(int(val))

            # Formatting Date
            formatted_date = str(ts)
            try:
                from datetime import datetime, timedelta
                dt_obj = datetime.strptime(ts, "%m/%d/%Y %I:%M:%S %p")
                # Format: "Yesterday • 11:05" or just "11:05" or "Day • Time"
                # User wants "Time below value". Reference shows "Yesterday • 11:05"
                # Let's try to match reference style
                now = datetime.now()
                # Simple relative check
                if dt_obj.date() == now.date():
                    # User request: Remove "Today", just show time
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

            # Create Attributed String
            # "68 mg/dl\nToaday • 11:05"
            full_str = f"{val_str} {unit}\n{date_str}"
            attr_str = NSMutableAttributedString.alloc().initWithString_(full_str)
            
            # Paragraph Style for Centering
            p_style = NSMutableParagraphStyle.alloc().init()
            p_style.setAlignment_(1) # Center
            # Add line height/spacing if needed
            p_style.setLineSpacing_(2)
            
            full_len = len(full_str)
            attr_str.addAttribute_value_range_(NSParagraphStyleAttributeName, p_style, (0, full_len))

            # Value Attributes (Dark Blue, Bold, Large)
            # "68"
            val_only_len = len(val_str)
            val_font = NSFont.boldSystemFontOfSize_(16.0)
            dark_blue = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.0, 0.25, 0.36, 1.0)
            attr_str.addAttribute_value_range_(NSFontAttributeName, val_font, (0, val_only_len))
            attr_str.addAttribute_value_range_(NSForegroundColorAttributeName, dark_blue, (0, val_only_len))
            
            # Unit Attributes (Dark Blue, Regular, Medium)
            # " mg/dl"
            unit_start = val_only_len
            unit_len = len(unit) + 1 # include space
            unit_font = NSFont.systemFontOfSize_(14.0)
            attr_str.addAttribute_value_range_(NSFontAttributeName, unit_font, (unit_start, unit_len))
            attr_str.addAttribute_value_range_(NSForegroundColorAttributeName, dark_blue, (unit_start, unit_len))
            
            # Date Attributes (Grey, Regular, Small)
            # "\nToday • 11:05"
            date_start = unit_start + unit_len
            date_len = len(full_str) - date_start
            date_font = NSFont.systemFontOfSize_(11.0)
            grey_color = NSColor.grayColor()
            attr_str.addAttribute_value_range_(NSFontAttributeName, date_font, (date_start, date_len))
            attr_str.addAttribute_value_range_(NSForegroundColorAttributeName, grey_color, (date_start, date_len))
                         
            self.tooltip_label.setAttributedStringValue_(attr_str)
            
            # Position tooltip
            tooltip_width = 105 # Reduced to 105 per user request to tighten padding
            t_x = px + 10 
            
            # Check if it goes off screen
            view_width = self.bounds().size.width
            if t_x + tooltip_width > view_width:
                # Clamp to right edge instead of flipping
                t_x = view_width - tooltip_width - 5
            
            if t_x < 0: t_x = 0
            
            t_y = py + 10
            # Increase height check for multi-line tooltip
            if t_y > self.bounds().size.height - 40: t_y = py - 40
            
            self.tooltip_container.setFrameOrigin_((t_x, t_y))
            # Resize tooltip frame to fit content
            self.tooltip_container.setFrameSize_(NSMakeRect(0, 0, tooltip_width, 45).size)
            self.tooltip_container.setHidden_(False)
        else:
            self.tooltip_container.setHidden_(True)
            
    # Required for events
    def acceptsFirstMouse_(self, event):
        return True

class CustomGraphView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(CustomGraphView, self).initWithFrame_(frame)
        if self:
            # 1. Background (Solid White handled by PlotView or just let it be transparent and PlotView fills)
            # We just need the plot view now.
            
            # 2. Plot View (Content)
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
        # Try to remove the system padding/chrome look by making the window white
        if self.window():
            self.window().setBackgroundColor_(NSColor.whiteColor())
            # self.window().setTitleVisibility_(1) # NSWindowTitleHidden = 1
            # self.window().setTitlebarAppearsTransparent_(True)

class MenuDelegate(NSObject):
    def initWithApp_(self, app):
         self = objc.super(MenuDelegate, self).init()
         self.app = app
         return self

    def menuWillOpen_(self, menu):
        # Trigger update when menu opens
        # This spawns a thread so it won't block open
        self.app.update_glucose(None)

# Set to True to use fake data and avoid API rate limits
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
        # icon=None ensures no icon in the menu bar, only text
        super(GlucoseApp, self).__init__("Schugaa", icon=None, quit_button=None)
        self.config = self.load_config()
        self.client = LibreClient(
            self.config.get("email"), 
            self.config.get("password"), 
            self.config.get("region", "eu")
        )
        # Clear default menu items
        self.menu = []
        self.quit_button = None
        
        # Setup Main Menu
        self.menu_handler = MenuActionHandler.alloc().initWithApp_(self)
        self.setup_application_menu()

        # Setup Status Bar Menu with Graph
        # We need a dummy menu item to hold the view
        self.graph_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        # Updated to 450x250 for better visibility
        self.graph_view = CustomGraphView.alloc().initWithFrame_(NSMakeRect(0, 0, 450, 250))
        self.graph_view.unit = self.config.get("unit", "mg/dL")
        self.graph_item.setView_(self.graph_view)
        
        # Add to the status item menu
        # self.menu is a rumps.Menu object, but we need to add a raw NSMenuItem or wrap it?
        # rumps doesn't easily support raw NSViews in its high-level abstraction
        # But we can access the underlying NSMenu via self._menu._menu
        self.menu.clear() # Ensure clean
        # We can try add a dummy item and replace it, or append direct to NSMenu
        # Safest way with rumps is to let rumps manage top level, but here we want to modify the status menu
        
        # Let's add the graph item directly to the status item's menu when we find it
        # Actually rumps creates self._menu (NSMenu) and assigns it.
        # We can append our item to self._menu._menu
        
        # Wait, rumps builds the menu on run? No, self._menu is initialized in App.__init__
        self._menu._menu.addItem_(self.graph_item)
        
        # Create custom status item with cream background
        self.status_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        self.status_menu_item.setEnabled_(False)
        
        # Create a view for the status item with cream background
        # Match graph width (450px) and increase height to eliminate bottom padding
        status_view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 450, 22))
        status_view.setWantsLayer_(True)
        # Cream color (RGB: 255, 253, 208)
        cream_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.992, 0.816, 1.0)
        status_view.layer().setBackgroundColor_(cream_color.CGColor())
        
        # Add three separate text fields with dynamic spacing
        label_y = 2
        label_height = 18
        font_size = 13.0
        text_color = NSColor.colorWithCalibratedWhite_alpha_(0.2, 1.0)
        font = NSFont.systemFontOfSize_(font_size)
        
        # 1. Status Label (Left) - Aligned Left (0)
        self.status_label = NSTextField.alloc().initWithFrame_(NSMakeRect(10, label_y, 130, label_height))
        self.status_label.setBezeled_(False)
        self.status_label.setDrawsBackground_(False)
        self.status_label.setEditable_(False)
        self.status_label.setSelectable_(False)
        self.status_label.setAlignment_(0) # Left
        self.status_label.setStringValue_("Status: OK")
        self.status_label.setFont_(font)
        self.status_label.setTextColor_(text_color)
        status_view.addSubview_(self.status_label)
        
        # 2. Last Updated Label (Center) - Aligned Center (1)
        self.last_update_label = NSTextField.alloc().initWithFrame_(NSMakeRect(140, label_y, 170, label_height))
        self.last_update_label.setBezeled_(False)
        self.last_update_label.setDrawsBackground_(False)
        self.last_update_label.setEditable_(False)
        self.last_update_label.setSelectable_(False)
        self.last_update_label.setAlignment_(1) # Center
        self.last_update_label.setStringValue_("Last updated: --")
        self.last_update_label.setFont_(font)
        self.last_update_label.setTextColor_(text_color)
        status_view.addSubview_(self.last_update_label)
        
        # 3. Sensor Label (Right) - Aligned Right (2)
        self.sensor_label = NSTextField.alloc().initWithFrame_(NSMakeRect(310, label_y, 130, label_height))
        self.sensor_label.setBezeled_(False)
        self.sensor_label.setDrawsBackground_(False)
        self.sensor_label.setEditable_(False)
        self.sensor_label.setSelectable_(False)
        self.sensor_label.setAlignment_(2) # Right
        self.sensor_label.setStringValue_("Sensor: --")
        self.sensor_label.setFont_(font)
        self.sensor_label.setTextColor_(text_color)
        status_view.addSubview_(self.sensor_label)
        
        self.status_menu_item.setView_(status_view)
        self._menu._menu.addItem_(self.status_menu_item)
        
        # Setup Delegate to refresh on open
        self.menu_delegate = MenuDelegate.alloc().initWithApp_(self)
        self._menu._menu.setDelegate_(self.menu_delegate)

        self.data_queue = queue.Queue()
        # Initial fetch
        self.update_glucose(None)
        
        # Start a background timer for periodic updates?
        # User requested update "when opened", but periodic is also good.
        # But for now, relying on open event as requested.
        # self.timer = rumps.Timer(self.update_glucose, 300) # Update every 5 minutes
        # self.timer.start()



    def setup_application_menu(self):
        try:
            main_menu = NSMenu.alloc().init()
            app_menu_item = NSMenuItem.alloc().init()
            app_menu_item.setTitle_("Schugaa")
            main_menu.addItem_(app_menu_item)
            
            app_menu = NSMenu.alloc().initWithTitle_("Schugaa")
            app_menu_item.setSubmenu_(app_menu)
            
            # Add Units Submenu
            units_item = NSMenuItem.alloc().init()
            units_item.setTitle_("Units")
            app_menu.addItem_(units_item)
            
            units_menu = NSMenu.alloc().initWithTitle_("Units")
            units_item.setSubmenu_(units_menu)
            
            # mg/dL Item
            mgdl_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("mg/dL", "setUnitMgdl:", "")
            mgdl_item.setTarget_(self.menu_handler)
            units_menu.addItem_(mgdl_item)
            
            # mmol/L Item
            mmol_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("mmol/L", "setUnitMmol:", "")
            mmol_item.setTarget_(self.menu_handler)
            units_menu.addItem_(mmol_item)
            
            app_menu.addItem_(NSMenuItem.separatorItem())

            # Add Refresh
            refresh_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Refresh Now", "refresh:", "r")
            refresh_item.setTarget_(self.menu_handler)
            app_menu.addItem_(refresh_item)
            
            # Add Logout
            logout_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Logout", "logout:", "")
            logout_item.setTarget_(self.menu_handler)
            app_menu.addItem_(logout_item)
            
            app_menu.addItem_(NSMenuItem.separatorItem())

            # Add Donate
            donate_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Donate", "donate:", "")
            donate_item.setTarget_(self.menu_handler)
            app_menu.addItem_(donate_item)
            
            # Add Share Debug Logs
            debug_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Share Debug Logs", "shareDebugLogs:", "")
            debug_item.setTarget_(self.menu_handler)
            app_menu.addItem_(debug_item)
            
            app_menu.addItem_(NSMenuItem.separatorItem())
            
            # Add Quit
            quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit Schugaa", "quit:", "q")
            quit_item.setTarget_(self.menu_handler)
            app_menu.addItem_(quit_item)
            
            NSApplication.sharedApplication().setMainMenu_(main_menu)
        except Exception as e:
            print(f"Failed to setup menu: {e}")

    def set_unit(self, unit):
        self.config["unit"] = unit
        write_json_secure(get_config_path(), self.config)
        
        # Update Graph View
        if hasattr(self, 'graph_view'):
            self.graph_view.unit = unit
            self.graph_view.setNeedsDisplay_(True)
            
        # Refresh UI (re-render with new unit)
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
            # Should not happen if we passed login
            return {}
            
        try:
            # Decode base64 credentials if they exist
            # Note: config is now a dictionary, not a file handle
            if "email" in config:
                try:
                    import base64
                    config["email"] = base64.b64decode(config["email"]).decode('utf-8')
                except:
                    pass # Maybe raw string

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
        # Allow manual refresh to bypass debounce slightly? 
        # Allow manual refresh to bypass debounce slightly (still capped)
        self.update_glucose(sender, force=True)

    def update_glucose(self, sender, force=False):
        # Debounce: Ensure at least 45 seconds between calls
        now = time.time()
        last = getattr(self, 'last_fetch_time', 0)
        if not force and now - last < 45:
            print(f"Skipping update (Debounce: {int(45 - (now - last))}s remaining)")
            return
        if force and now - last < 10:
            print(f"Skipping update (Force Debounce: {int(10 - (now - last))}s remaining)")
            return
             
        self.last_fetch_time = now
        
        # Run in a separate thread to avoid blocking the UI
        thread = threading.Thread(target=self._fetch_and_update, daemon=True)
        thread.start()

    def _fetch_and_update(self):
        try:
            if USE_DUMMY_DATA:
                print("Generating dummy data...")
                data = self.generate_dummy_data()
                # Simulate network delay
                time.sleep(0.5)
            else:
                if not self.client:
                   self.client = LibreClient(
                       self.config.get("email"),
                       self.config.get("password"),
                       self.config.get("region", "eu")
                   )
                
                print("Fetching glucose data...")
                # Pass retry=True to handle re-login automatically
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
        # Generate a sine wave pattern mixed with random noise
        # This creates a realistic looking smooth curve
        import math
        import random
        from datetime import datetime, timedelta
        
        # Use a fixed reference start so graph is stable-ish or moving?
        # Let's use current time for moving graph
        now = datetime.now()
        base_glucose = 120
        amplitude = 40
        period_minutes = 120 # 2 hour cycle
        
        # Calculate current value based on time
        minutes = now.hour * 60 + now.minute
        val = base_glucose + amplitude * math.sin(2 * math.pi * minutes / period_minutes)
        # Add small noise
        val += random.uniform(-5, 5)
        
        # Trend arrow (derivative rough approximation)
        # Next value in 5 mins
        next_minutes = minutes + 5
        next_val = base_glucose + amplitude * math.sin(2 * math.pi * next_minutes / period_minutes)
        diff = next_val - val
        
        # Trend arrow (derivative rough approximation)
        # 1: ↓, 2: ↘, 3: →, 4: ↗, 5: ↑
        if diff > 2: trend = 5 # Rising quickly (↑)
        elif diff > 1: trend = 4 # Rising (↗)
        elif diff < -2: trend = 1 # Falling quickly (↓)
        elif diff < -1: trend = 2 # Falling (↘)
        else: trend = 3 # Stable
        
        # Color
        color = 1 # Green
        if val > 180 or val < 70: color = 2 # Yellow
        if val > 240 or val < 54: color = 3 # Red
        
        # Graph History (past 4 hours)
        history = []
        for i in range(50): # 50 points * 5 mins roughly = 4 hours
            t_offset = i * 5
            hist_time = now - timedelta(minutes=t_offset)
            h_mins = hist_time.hour * 60 + hist_time.minute
            
            h_val = base_glucose + amplitude * math.sin(2 * math.pi * h_mins / period_minutes)
            h_val += random.uniform(-3, 3)
            
            # Format timestamp as expected by API: "1/31/2026 8:25:41 AM"
            ts_str = hist_time.strftime("%-m/%-d/%Y %-I:%M:%S %p")
            
            history.append({
                'Value': h_val,
                'Timestamp': ts_str
            })
        
        history.reverse() # Oldest first
        
        # Sensor data - OPTION 1: Simulate warmup (activated 30 minutes ago)
        sensor_activated = int(time.time()) - (30 * 60)  # Activated 30 mins ago
        sensor_expires = sensor_activated + (14 * 24 * 60 * 60)  # Expires in ~14 days
        
        # OPTION 2: Simulate normal sensor (uncomment to test)
        # sensor_activated = int(time.time()) - (4 * 24 * 60 * 60)  # Activated 4 days ago
        # sensor_expires = sensor_activated + (14 * 24 * 60 * 60)  # Expires in 10 days
        
        return {
            'Value': val,
            'Trend': trend,
            'TrendArrow': trend, # For compatibility
            'Color': color,
            'GraphData': history,
            'Unit': self.config.get("unit", "mg/dL"),
            'SensorActivated': sensor_activated,
            'SensorExpires': sensor_expires
        }
            
    def _update_ui_with_data(self, data):
        try:
            if not data:
                # If we already have a value, keep it to mask transient errors
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
                
            # Update Graph
            graph_data = data.get("GraphData", [])
            if hasattr(self, 'graph_view'):
                self.graph_view.update_data(graph_data)
                
            trend = data.get("TrendArrow")
            if hasattr(self, 'graph_view'):
                self.graph_view.set_trend(trend)

            arrow = self.TREND_ARROWS.get(trend, "")
            
            # Unit Handling
            unit = self.config.get("unit", "mg/dL")
            disp_val = to_display_value(value, unit)
            val_str = f"{disp_val:.1f}" if unit == "mmol/L" else str(int(disp_val))
            
            # Simple title: "5.8 →" or "105 →"
            title_str = f" {val_str} {arrow} "
            
            # Determine text color (Logic expects mg/dL)
            text_color = None
            
            # Helper to safely get color or fallback
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
                else: # > 250
                    text_color = NSColor.redColor()

            except Exception:
                # Fallback if AppKit is not defined or other error
                self.title = title_str
                return
                
            # Create attributed string
            attrs = {
                NSForegroundColorAttributeName: text_color,
                NSFontAttributeName: NSFont.boldSystemFontOfSize_(14.0) # Slightly smaller font
            }
            ns_title = NSString.stringWithString_(title_str)
            attr_str = NSAttributedString.alloc().initWithString_attributes_(ns_title, attrs)
            
            # Improved Status Item Discovery from rumps source
            status_item = None
            if hasattr(self, '_nsapp') and hasattr(self._nsapp, 'nsstatusitem'):
                status_item = self._nsapp.nsstatusitem
            
            # Fallback (old methods)
            if not status_item and hasattr(self, '_nsstatusitem'):
                status_item = self._nsstatusitem
            elif hasattr(self, '_status_item'):
                status_item = self._status_item
            
            # Method 2: Traverse rumps internals (App -> ApplicationSupport -> NSStatusItem)
            if not status_item:
                 try:
                     # In recent rumps, self._application_support is the specific helper
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
                 # Color setting not supported by this rumps version without access to NSStatusItem
                 self.title = title_str

            # Update status/last updated items
            try:
                from datetime import datetime
                self.last_updated_at = datetime.now()
                # Update status with sensor info combined
                if hasattr(self, "status_label"):
                    sensor_text = "--"
                    sensor_activated = data.get("SensorActivated")
                    sensor_expires = data.get("SensorExpires")
                    
                    if sensor_activated:
                        now_ts = time.time()
                        # LibreLink sensors have 60-minute warmup period
                        warmup_duration = 60 * 60  # 60 minutes in seconds
                        warmup_end = sensor_activated + warmup_duration
                        
                        # Check if sensor is still warming up
                        if now_ts < warmup_end:
                            minutes_remaining = int((warmup_end - now_ts) / 60)
                            if minutes_remaining == 0:
                                sensor_text = "Warming up (<1 min)"
                            elif minutes_remaining == 1:
                                sensor_text = "Warming up (1 min)"
                            else:
                                sensor_text = f"Warming up ({minutes_remaining} min)"
                        elif sensor_expires:
                            # Warmup complete, show expiration countdown
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
                        # Fallback if activation time not available
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
                     
                    # Update each label separately with dynamic spacing
                    self.status_label.setStringValue_("Status: OK")
                    if hasattr(self, "last_update_label"):
                        self.last_update_label.setStringValue_(f"Last updated: {self.last_updated_at.strftime('%H:%M')}")
                    if hasattr(self, "sensor_label"):
                        self.sensor_label.setStringValue_(f"Sensor: {sensor_text}")
            except Exception:
                pass
                 
        except Exception as e:
            pass
            self.title = "Err"
            

def get_config_path():
    # Helper to get the config path in a standard location
    # 1. ~/.schugaa/config.json
    # 2. current directory config.json (legacy/dev)
    
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
    
    # Simple redirector that writes to both terminal and file
    class DualWriter:
        def __init__(self, original_stream, file_path):
            self.original_stream = original_stream
            self.file = open(file_path, "a", buffering=1) # Line buffered
            
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
    # Try finding config in standard path first
    config_path = get_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except:
            pass
            
    # Fallback to resource_path for bundled readonly config or dev mode
    try:
        with open(resource_path("config.json"), "r") as f:
            return json.load(f)
    except:
        return None


if __name__ == "__main__":
    setup_logging()

    # Ensure Dock icon is set
    set_dock_icon()
    
    # FIX: Force App Name to Schugaa
    try:
        from Foundation import NSBundle
        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info:
            info['CFBundleName'] = 'Schugaa'
    except Exception as e:
        pass
    
    # Check if config exists and has email/password

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
        
    # Define login logic with unified AppKit Window
    def perform_login():
        try:
            from AppKit import (NSAlert, NSView, NSTextField, NSSecureTextField, NSPopUpButton, 
                              NSMakeRect, NSStackView, NSUserInterfaceLayoutOrientationVertical,
                              NSLayoutAttributeLeading, NSLayoutAttributeTrailing, NSLayoutAttributeTop,
                              NSLayoutAttributeBottom, NSLayoutAttributeWidth, NSLayoutRelationEqual,
                              NSImage, NSApplication, NSRunningApplication, NSApplicationActivateIgnoringOtherApps) 
            import objc
        except ImportError:
            # Fallback for dev environment strictness
            rumps.alert("Error", "Missing AppKit. Please ensure pyobjc-framework-Cocoa is installed.")
            return False

        # Create the Alert Container
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

        # Create a container view
        wrapper_frame = NSMakeRect(0, 0, 300, 120)
        wrapper_view = NSView.alloc().initWithFrame_(wrapper_frame)

        # Labels (Optional, but good for UX? simplified to Placeholders as requested)
        
        # Region Dropdown (Top)
        region_popup = NSPopUpButton.alloc().initWithFrame_(NSMakeRect(10, 80, 135, 24))
        regions = ['eu', 'us', 'au', 'ca', 'global', 'de', 'fr', 'jp', 'ap', 'ae', 'la', 'eu2', 'gb', 'ru', 'tw', 'kr']
        region_popup.addItemsWithTitles_(regions)
        region_popup.selectItemWithTitle_("eu")
        
        # Unit Dropdown (Top Right)
        unit_popup = NSPopUpButton.alloc().initWithFrame_(NSMakeRect(155, 80, 135, 24))
        units = ['mg/dL', 'mmol/L']
        unit_popup.addItemsWithTitles_(units)
        unit_popup.selectItemWithTitle_("mg/dL")
        
        # Email Field (Middle)
        email_field = NSTextField.alloc().initWithFrame_(NSMakeRect(10, 50, 280, 24))
        email_field.setPlaceholderString_("LibreLinkUp Email")
        
        # Password Field (Bottom)
        pass_field = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(10, 20, 280, 24))
        pass_field.setPlaceholderString_("LibreLinkUp Password")
        
        wrapper_view.addSubview_(region_popup)
        wrapper_view.addSubview_(unit_popup)
        wrapper_view.addSubview_(email_field)
        wrapper_view.addSubview_(pass_field)
        
        alert.setAccessoryView_(wrapper_view)
        
        # Window logic Loop
        # Ensure app is active and in front using NSRunningApplication
        NSApplication.sharedApplication().setActivationPolicy_(0) # NSApplicationActivationPolicyRegular
        NSRunningApplication.currentApplication().activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        
        while True:
            # Re-activate just in case
            NSRunningApplication.currentApplication().activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            
            response = alert.runModal()
            
            if response == 1000: # First Button (Login)
                email = email_field.stringValue().strip()
                password = pass_field.stringValue().strip()
                region = region_popup.selectedItem().title()
                unit = unit_popup.selectedItem().title()
                
                if not email or not password:
                    continue
                
                # Test credentials
                try:
                    # Explicitly login to check success and get region
                    client = LibreClient(email, password, region)
                    if not client.login():
                        rumps.alert("Login Failed", "Could not authenticate with LibreLinkUp. Check credentials or try another region.")
                        continue
                        
                    # Fetch data to be sure
                    client.get_latest_glucose()
                    
                    # Save Config - Use client.region in case of redirect
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
                # Cancel clicked
                return False

    # Main Execution
    if needs_login:
        if not perform_login():
            sys.exit(0)
            
    GlucoseApp().run()
