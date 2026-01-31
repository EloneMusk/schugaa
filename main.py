import rumps
import json
import threading
import os
import sys
from libre_api import LibreClient
from AppKit import (NSImage, NSApplication, NSMenu, NSMenuItem, NSObject, NSView, NSBezierPath, 
                   NSTrackingArea, NSTextField, NSColor, NSFont, NSString,
                   NSTrackingMouseEnteredAndExited, NSTrackingMouseMoved, 
                   NSTrackingActiveInKeyWindow, NSTrackingActiveAlways, NSTrackingInVisibleRect,
                   NSMutableAttributedString, NSFontAttributeName, NSForegroundColorAttributeName,
                   NSParagraphStyleAttributeName, NSMutableParagraphStyle, NSWorkspace)
from Foundation import NSMakeRect, NSURL
import objc

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

class CustomGraphView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(CustomGraphView, self).initWithFrame_(frame)
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
            
            # Tooltip text field - Pill Shape
            self.tooltip = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 35))
            self.tooltip.setBezeled_(False)
            self.tooltip.setDrawsBackground_(False)
            self.tooltip.setBackgroundColor_(NSColor.clearColor())
            self.tooltip.setTextColor_(NSColor.blackColor())
            self.tooltip.setEditable_(False)
            self.tooltip.setSelectable_(False)
            self.tooltip.setHidden_(True)
            self.tooltip.setWantsLayer_(True)
            self.tooltip.layer().setCornerRadius_(10)
            self.tooltip.layer().setShadowOpacity_(0.2)
            self.tooltip.layer().setShadowOffset_((0, -2))
            self.tooltip.layer().setShadowRadius_(4)
            self.addSubview_(self.tooltip)
            
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

        # White Background
        NSColor.whiteColor().set()
        NSBezierPath.fillRect_(rect)
        
        width = rect.size.width
        height = rect.size.height
        
        # Dimensions & Scaling
        is_mmol = getattr(self, 'unit', 'mg/dL') == 'mmol/L'
        factor = 18.0182 if is_mmol else 1.0
        
        # Range matching the image roughly (50 used as base, up to 300+)
        if is_mmol:
            max_y_val = 21.0
            min_y_val = 0.0
            grid_values = [3, 6, 9, 12, 15, 18, 21]
            band_target_top = 10.0 
            band_target_bot = 3.9
            band_high_top = 13.9 
        else:
            max_y_val = 320 # Give some headroom
            min_y_val = 50  # Start from 50 to focus view
            grid_values = [100, 150, 200, 250, 300]
            # Bands
            band_target_top = 180
            band_target_bot = 70
            band_high_top = 250

        y_range = max_y_val - min_y_val
        
        # Margins for Axis Labels
        margin_left = 35 # Reduced padding
        margin_right = 20
        margin_top = 30
        margin_bottom = 40
        
        plot_width = width - margin_left - margin_right
        plot_height = height - margin_bottom - margin_top
        
        def get_y(val):
            # Clamp for drawing logic
            val_clamped = max(min(val, max_y_val), min_y_val)
            normalized = (val_clamped - min_y_val) / y_range
            return margin_bottom + normalized * plot_height

        def get_x(index, total):
            step = plot_width / max(total - 1, 1) if total > 1 else 0
            return margin_left + index * step

        # --- 1. Background Bands ---
        
        # Green Band (Target)
        y_t_top = get_y(band_target_top)
        y_t_bot = get_y(band_target_bot)
        # Check if visible
        if y_t_top > margin_bottom:
             g_rect = NSMakeRect(margin_left, y_t_bot, plot_width, y_t_top - y_t_bot)
             # Light Green
             NSColor.colorWithCalibratedRed_green_blue_alpha_(0.5, 0.9, 0.5, 0.5).set()
             NSBezierPath.fillRect_(g_rect)

        # Yellow Band (High)
        y_h_top = get_y(band_high_top)
        # Draw from target top to high top
        if y_h_top > y_t_top:
             y_rect = NSMakeRect(margin_left, y_t_top, plot_width, y_h_top - y_t_top)
             # Light Yellow
             NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.9, 0.4, 0.5).set()
             NSBezierPath.fillRect_(y_rect)

        # --- 2. Grid Lines (Horizontal Dashed) ---
        grid_color = NSColor.colorWithCalibratedWhite_alpha_(0.7, 1.0)
        grid_path = NSBezierPath.bezierPath()
        grid_path.setLineWidth_(1.0)
        grid_path.setLineDash_count_phase_([4.0, 4.0], 2, 0.0)
        
        # Font Attributes
        axis_font = NSFont.systemFontOfSize_(10)
        axis_attrs = {
            NSFontAttributeName: axis_font, 
            NSForegroundColorAttributeName: NSColor.blackColor()
        }
        # Right aligned for Y-axis labels
        p_style = NSMutableParagraphStyle.alloc().init()
        p_style.setAlignment_(2) # Right
        y_label_attrs = {
            NSFontAttributeName: axis_font, 
            NSForegroundColorAttributeName: NSColor.blackColor(),
            NSParagraphStyleAttributeName: p_style
        }

        for val in grid_values:
            y = get_y(val)
            if y > margin_bottom and y < height - margin_top:
                # Line
                grid_path.moveToPoint_((margin_left, y))
                grid_path.lineToPoint_((width - margin_right, y))
                
                # Label
                l_str = str(val)
                s = NSString.stringWithString_(l_str).sizeWithAttributes_(y_label_attrs)
                # Draw to left of axis
                r = NSMakeRect(0, y - s.height/2, margin_left - 5, s.height)
                NSString.stringWithString_(l_str).drawInRect_withAttributes_(r, y_label_attrs)
                
        grid_color.set()
        grid_path.stroke()

        # --- 3. Axes (Solid Black) ---
        axis_path = NSBezierPath.bezierPath()
        axis_path.setLineWidth_(1.5)
        # Y Axis
        axis_path.moveToPoint_((margin_left, margin_bottom))
        axis_path.lineToPoint_((margin_left, height - margin_top))
        # X Axis
        axis_path.moveToPoint_((margin_left, margin_bottom))
        axis_path.lineToPoint_((width - margin_right, margin_bottom))
        
        NSColor.blackColor().set()
        axis_path.stroke()
        
        # Axis Titles
        # Y Title "(mg/dL)"
        title_str = "(mg/dL)"
        t_size = NSString.stringWithString_(title_str).sizeWithAttributes_(axis_attrs)
        # Draw upright above Y axis
        NSString.stringWithString_(title_str).drawAtPoint_withAttributes_((5, height - margin_top + 5), axis_attrs)
        
        # X Title "Time" - Bottom Center
        x_title = "Time"
        xt_size = NSString.stringWithString_(x_title).sizeWithAttributes_(axis_attrs)
        NSString.stringWithString_(x_title).drawAtPoint_withAttributes_((margin_left + plot_width/2 - xt_size.width/2, 5), axis_attrs)


        # --- 4. Data Plot ---
        if len(self.data_points) < 2: return
        
        points_coords = []
        count = len(self.data_points)
        
        # Calculate coords
        for i in range(count):
            val, ts = self.data_points[i]
            disp_val = val / factor
            x = get_x(i, count)
            y = get_y(disp_val)
            points_coords.append((x, y, disp_val, ts, val))

        # A. Connection Line (Black)
        line_path = NSBezierPath.bezierPath()
        for i, (x, y, _, _, _) in enumerate(points_coords):
            if i == 0: line_path.moveToPoint_((x, y))
            else: line_path.lineToPoint_((x, y))
            
        NSColor.blackColor().set()
        line_path.setLineWidth_(2.0)
        line_path.stroke()
        
        # B. End Dot Only
        if points_coords:
            x, y, _, _, raw_val = points_coords[-1]
            dot_rect = NSMakeRect(x - 4, y - 4, 8, 8)
            dot_path = NSBezierPath.bezierPathWithOvalInRect_(dot_rect)
            
            # Fill with status color
            c = self.get_color(raw_val)
            c.set()
            dot_path.fill()
            
            # Border
            NSColor.blackColor().set()
            dot_path.setLineWidth_(1.5)
            dot_path.stroke()

        # 5. Save coords for hover
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
                    r = NSMakeRect(x - s.width/2, margin_bottom - 15, s.width, s.height)
                    NSString.stringWithString_(t_lbl).drawInRect_withAttributes_(r, axis_attrs)
                    
                    # Tick mark
                    tick = NSBezierPath.bezierPath()
                    tick.moveToPoint_((x, margin_bottom))
                    tick.lineToPoint_((x, margin_bottom - 3))
                    tick.setLineWidth_(1.0)
                    tick.stroke()
                except: pass
                
        # Hover Line (Black)
        if self.hover_point:
             hx, hy = self.hover_point
             NSColor.blackColor().set()
             path = NSBezierPath.bezierPathWithRect_(NSMakeRect(hx-0.5, margin_bottom, 1, plot_height))
             path.fill()

    def mouseMoved_(self, event):
        if not hasattr(self, 'points_coords') or not self.points_coords:
            self.tooltip.setHidden_(True)
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
            # Input format example: "1/31/2026 8:25:41 AM"
            formatted_date = str(ts)
            try:
                from datetime import datetime
                # Parse
                dt_obj = datetime.strptime(ts, "%m/%d/%Y %I:%M:%S %p")
                # Format to ddmmyyyy (or dd.mm.yyyy) + time
                formatted_date = dt_obj.strftime("%d.%m.%Y %H:%M")
            except Exception as e:
                pass # Keep original string on failure

            # Create Attributed String
            # Value: 15pt (75% of 20)
            # Date: 10pt (50% of 20)
            
            full_str = f"{val_str}\n{formatted_date}"
            attr_str = NSMutableAttributedString.alloc().initWithString_(full_str)
            
            # Value Attributes (0 to len(val_str))
            val_len = len(val_str)
            val_font = NSFont.boldSystemFontOfSize_(15.0)
            attr_str.addAttribute_value_range_(NSFontAttributeName, val_font, (0, val_len))
            attr_str.addAttribute_value_range_(NSForegroundColorAttributeName, NSColor.blackColor(), (0, val_len))
            
            # Date Attributes (next part)
            date_range = (val_len + 1, len(formatted_date))
            date_font = NSFont.systemFontOfSize_(10.0)
            attr_str.addAttribute_value_range_(NSFontAttributeName, date_font, date_range)
            attr_str.addAttribute_value_range_(NSForegroundColorAttributeName, NSColor.blackColor(), date_range) # or gray
            
            self.tooltip.setAttributedStringValue_(attr_str)
            
            # Position tooltip
            tooltip_width = 150
            t_x = px + 10 # Default to right of point
            
            # Check if it goes off screen
            view_width = self.bounds().size.width
            if t_x + tooltip_width > view_width:
                # Clamp to right edge instead of flipping
                t_x = view_width - tooltip_width - 5
            
            if t_x < 0: t_x = 0
            
            t_y = py + 10
            # Increase height check for multi-line tooltip
            if t_y > self.bounds().size.height - 40: t_y = py - 40
            
            self.tooltip.setFrameOrigin_((t_x, t_y))
            # Resize tooltip frame to fit content
            self.tooltip.setFrameSize_(NSMakeRect(0, 0, tooltip_width, 50).size)
            self.tooltip.setHidden_(False)
        else:
            self.tooltip.setHidden_(True)
            
    # Required for events
    def acceptsFirstMouse_(self, event):
        return True

class MenuDelegate(NSObject):
    def initWithApp_(self, app):
         self = objc.super(MenuDelegate, self).init()
         self.app = app
         return self

    def menuWillOpen_(self, menu):
        # Trigger update when menu opens
        # This spawns a thread so it won't block open
        self.app.update_glucose(None)

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
        super(GlucoseApp, self).__init__("Created with Love", icon=None, quit_button=None)
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
        self.graph_view = CustomGraphView.alloc().initWithFrame_(NSMakeRect(0, 0, 300, 150))
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
        
        # Setup Delegate to refresh on open
        self.menu_delegate = MenuDelegate.alloc().initWithApp_(self)
        self._menu._menu.setDelegate_(self.menu_delegate)

        self.data_queue = queue.Queue()
        # Initial fetch
        self.update_glucose(None)
        
        # Start a background timer for periodic updates?
        # User requested update "when opened", but periodic is also good.
        # But for now, relying on open event as requested.
        self.timer = rumps.Timer(self.update_glucose, 300) # Update every 5 minutes
        self.timer.start()



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
        with open(get_config_path(), "w") as f:
            json.dump(self.config, f, indent=4)
        
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

            return config
        except Exception as e:
            rumps.alert("Error", f"Could not process config: {e}")
            return {}

    @rumps.timer(30)
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
        self.update_glucose(sender)

    def update_glucose(self, sender):
        # Run in a separate thread to avoid blocking the UI
        thread = threading.Thread(target=self._fetch_and_update)
        thread.start()

    def _fetch_and_update(self):
        try:
            data = self.client.get_latest_glucose()
            self.data_queue.put(data)
        except Exception as e:
            # Optionally signal error to UI or just log silently
            pass
            
    def _update_ui_with_data(self, data):
        try:
            if not data:
                self.title = "???"
                return

            value = data.get("Value")
            if value is None:
                self.title = "???"
                return
                
            # Update Graph
            graph_data = data.get("GraphData", [])
            if hasattr(self, 'graph_view'):
                self.graph_view.update_data(graph_data)
                
            trend = data.get("TrendArrow")
            arrow = self.TREND_ARROWS.get(trend, "")
            
            # Unit Handling
            unit = self.config.get("unit", "mg/dL")
            if unit == "mmol/L":
                disp_val = value / 18.0182
                val_str = f"{disp_val:.1f}"
            else:
                val_str = str(value)
            
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
                 print("DEBUGGING: Could not find NSStatusItem to apply color")
                 self.title = title_str
                 
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
    if config and "email" in config and "password" in config:
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
        regions = ['eu', 'global', 'de', 'fr', 'jp', 'ap', 'ae']
        region_popup.addItemsWithTitles_(regions)
        region_popup.selectItemWithTitle_("eu")
        
        # Unit Dropdown (Top Right)
        unit_popup = NSPopUpButton.alloc().initWithFrame_(NSMakeRect(155, 80, 135, 24))
        units = ['mg/dL', 'mmol/L']
        unit_popup.addItemsWithTitles_(units)
        unit_popup.selectItemWithTitle_("mg/dL")
        
        # Email Field (Middle)
        email_field = NSTextField.alloc().initWithFrame_(NSMakeRect(10, 50, 280, 24))
        email_field.setPlaceholderString_("Email")
        
        # Password Field (Bottom)
        pass_field = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(10, 20, 280, 24))
        pass_field.setPlaceholderString_("Password")
        
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
                    client = LibreClient(email, password, region)
                    client.get_latest_glucose()
                    
                    # Save Config
                    import base64
                    email_b64 = base64.b64encode(email.encode('utf-8')).decode('utf-8')
                    password_b64 = base64.b64encode(password.encode('utf-8')).decode('utf-8')
                    
                    config = {
                        "email": email_b64,
                        "password": password_b64,
                        "region": region,
                        "unit": unit
                    }
                    
                    with open(get_config_path(), "w") as f:
                        json.dump(config, f, indent=4)
                        
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
