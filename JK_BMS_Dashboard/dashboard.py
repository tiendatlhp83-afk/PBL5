import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial
import serial.tools.list_ports
import threading
import re
import csv
import os
from datetime import datetime
from collections import deque
from PIL import Image, ImageTk

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

BAUD_RATE = 115200

class BMSDashboardPRO:
    def __init__(self, root):
        self.root = root
        self.root.title("JK BMS Professional Dashboard")
        self.root.geometry("1200x700")
        
        self.serial_conn = None
        self.is_running = True
        self.is_connected = False
        self.is_logging = False
        self.csv_file = ""
        
        self.time_data = deque(maxlen=50)
        self.vol_data = deque(maxlen=50)
        self.cur_data = deque(maxlen=50)
        
        self.current_data = {
            "vol": 0.0, "cur": 0.0, "soc": 0,
            "cells": [0.0] * 16,
            "updated": False
        }
        
        self.setup_ui()
        self.scan_ports()
        self.update_gui_loop()

    def setup_ui(self):
        # --- TOP CONTAINER (Chứa 3 phần Trái - Giữa - Phải) ---
        top_container = tk.Frame(self.root)
        top_container.pack(fill="x", padx=10, pady=5)

        # 1. TOP LEFT (Chứa Điều khiển & Thông số hệ thống - Thu gọn)
        # Bỏ expand=True và fill="both" để khung tự động ôm sát nội dung (ngang bằng SOC)
        top_left_frame = tk.Frame(top_container)
        top_left_frame.pack(side="left", anchor="nw")

        # 1.1 Control frame
        ctrl_frame = tk.Frame(top_left_frame, pady=5)
        ctrl_frame.pack(anchor="w")
        
        tk.Label(ctrl_frame, text="Cổng COM:").pack(side="left")
        self.cb_ports = ttk.Combobox(ctrl_frame, width=15, state="readonly")
        self.cb_ports.pack(side="left", padx=5)
        
        tk.Button(ctrl_frame, text="🔄 Làm mới", command=self.scan_ports).pack(side="left", padx=5)
        
        self.btn_connect = tk.Button(ctrl_frame, text="▶ Bắt đầu", bg="green", fg="white", command=self.toggle_connection)
        self.btn_connect.pack(side="left", padx=15)

        # 1.2 Summary frame - Thu gọn ôm sát chữ SOC
        summary_frame = tk.LabelFrame(top_left_frame, text="Thông số Hệ thống", font=('Arial', 10, 'bold'), padx=10, pady=5)
        summary_frame.pack(anchor="w", pady=5)

        self.lbl_total_vol = tk.Label(summary_frame, text="Total Vol: -- V", font=('Arial', 14, 'bold'), fg="blue", width=16)
        self.lbl_total_vol.grid(row=0, column=0)

        self.lbl_current = tk.Label(summary_frame, text="Current: -- A", font=('Arial', 14, 'bold'), fg="red", width=16)
        self.lbl_current.grid(row=0, column=1)
        
        self.lbl_soc = tk.Label(summary_frame, text="SOC: -- %", font=('Arial', 14, 'bold'), fg="green", width=16)
        self.lbl_soc.grid(row=0, column=2)

        # 2. TOP CENTER (Trường Đại học)
        top_center_frame = tk.Frame(top_container)
        top_center_frame.pack(side="left", expand=True, fill="both")
        
        lbl_uni = tk.Label(top_center_frame, text="TRƯỜNG ĐẠI HỌC BÁCH KHOA - ĐẠI HỌC ĐÀ NẴNG", 
                           font=('Arial', 14, 'bold'), fg="#004080")
        lbl_uni.pack(expand=True)

        # 3. TOP RIGHT (Chứa Danh sách tên & Logo)
        top_right_frame = tk.Frame(top_container)
        top_right_frame.pack(side="right", anchor="ne")

        # 3.1 Khung hiển thị Tên
        names_frame = tk.Frame(top_right_frame)
        names_frame.pack(side="left", padx=20, anchor="e")
        
        team_members = [
            "Nguyễn Tiến Đạt",
            "Lê Nhật Tân",
            "Lê Nguyễn Đan Huy",
            "Lê Minh Kiên"
        ]
        for name in team_members:
            tk.Label(names_frame, text=name, font=('Arial', 11, 'bold'), fg="#333333").pack(anchor="e", pady=1)

        # 3.2 Logo
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            img_path = os.path.join(current_dir, "ckgt.jpg")
            
            img = Image.open(img_path)
            aspect_ratio = img.width / img.height
            new_height = 140 
            new_width = int(new_height * aspect_ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.logo_photo = ImageTk.PhotoImage(img)
            lbl_logo = tk.Label(top_right_frame, image=self.logo_photo)
            lbl_logo.pack(side="right")
        except Exception as e:
            print("Không thể tải logo:", e)
            tk.Label(top_right_frame, text="[Logo Khuyết]", fg="gray", width=15, height=8, relief="solid").pack(side="right")


        # --- BOTTOM FRAME (Nằm dưới cùng, chứa trạng thái và nút Lưu) ---
        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(side="bottom", fill="x", padx=15, pady=10)

        self.lbl_status = tk.Label(bottom_frame, text="Sẵn sàng.", font=('Arial', 10, 'italic'), fg="gray")
        self.lbl_status.pack(side="left", anchor="w")

        self.btn_log = tk.Button(bottom_frame, text="💾 Lưu Dữ Liệu", font=('Arial', 11, 'bold'),
                                 bg="#008CBA", fg="white", activebackground="#005f7a", activeforeground="white",
                                 relief="raised", bd=3, padx=25, pady=8, cursor="hand2", command=self.toggle_logging)
        self.btn_log.pack(side="right")

        # --- MAIN GRAPHS FRAME (Split Left/Right) ---
        main_graph_frame = tk.Frame(self.root)
        main_graph_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # LEFT SIDE: Total Vol & Current (2 rows)
        left_frame = tk.Frame(main_graph_frame)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.fig_left = Figure(figsize=(6, 4), dpi=100)
        self.ax_vol = self.fig_left.add_subplot(211)
        self.ax_cur = self.fig_left.add_subplot(212)
        self.fig_left.tight_layout(pad=3.0)
        
        self.canvas_left = FigureCanvasTkAgg(self.fig_left, master=left_frame)
        self.canvas_left.get_tk_widget().pack(fill="both", expand=True)

        # RIGHT SIDE: 16 Cells Bar Chart (1 row)
        right_frame = tk.Frame(main_graph_frame)
        right_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))

        self.fig_right = Figure(figsize=(6, 4), dpi=100)
        self.ax_cells = self.fig_right.add_subplot(111)
        self.fig_right.tight_layout(pad=3.0)

        self.canvas_right = FigureCanvasTkAgg(self.fig_right, master=right_frame)
        self.canvas_right.get_tk_widget().pack(fill="both", expand=True)


    def scan_ports(self):
        ports = serial.tools.list_ports.comports()
        port_list = [port.device for port in ports]
        self.cb_ports['values'] = port_list
        if port_list:
            self.cb_ports.current(0)
        else:
            self.cb_ports.set("Không tìm thấy COM")

    def toggle_connection(self):
        if not self.is_connected:
            selected_port = self.cb_ports.get()
            if not selected_port or selected_port == "Không tìm thấy COM":
                messagebox.showwarning("Cảnh báo", "Vui lòng chọn cổng COM hợp lệ!")
                return
            try:
                self.serial_conn = serial.Serial(selected_port, BAUD_RATE, timeout=1)
                self.is_connected = True
                self.btn_connect.config(text="⏹ Dừng", bg="red")
                self.lbl_status.config(text=f"Đã kết nối {selected_port}", fg="green")
                threading.Thread(target=self.read_serial_data, daemon=True).start()
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể kết nối {selected_port}\n{e}")
        else:
            self.is_connected = False
            if self.serial_conn:
                self.serial_conn.close()
            self.btn_connect.config(text="▶ Bắt đầu", bg="green")
            self.lbl_status.config(text="Đã ngắt kết nối.", fg="red")

    def toggle_logging(self):
        if not self.is_logging:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV Files", "*.csv")],
                title="Chọn nơi lưu file Log"
            )
            if file_path:
                self.csv_file = file_path
                self.is_logging = True
                self.btn_log.config(text="⏹ Đang Lưu Dữ Liệu... (Nhấn để dừng)", bg="#D83B01", fg="white")
                with open(self.csv_file, mode='w', newline='') as file:
                    writer = csv.writer(file)
                    headers = ["Thời gian", "Tổng Áp (V)", "Dòng Điện (A)", "SOC (%)"] + [f"Cell {i+1} (V)" for i in range(16)]
                    writer.writerow(headers)
        else:
            self.is_logging = False
            self.btn_log.config(text="💾 Lưu Dữ Liệu", bg="#008CBA", fg="white")
            messagebox.showinfo("Thông báo", f"Đã lưu thành công tại:\n{self.csv_file}")

    def read_serial_data(self):
        regex_summary = r"Total Voltage:\s*([\d.]+).*?Current:\s*([-\d.]+).*?SOC:\s*(\d+)"
        regex_cell = r"C(\d{2}):\s*([\d.]+)"

        while self.is_running and self.is_connected:
            try:
                line = self.serial_conn.readline().decode('utf-8').strip()
                if not line: continue

                match_summary = re.search(regex_summary, line)
                if match_summary:
                    self.current_data["vol"] = float(match_summary.group(1))
                    self.current_data["cur"] = float(match_summary.group(2))
                    self.current_data["soc"] = int(match_summary.group(3))
                    self.current_data["updated"] = True 

                for match in re.finditer(regex_cell, line):
                    idx = int(match.group(1)) - 1
                    if 0 <= idx < 16:
                        self.current_data["cells"][idx] = float(match.group(2))

            except Exception:
                pass

    def update_gui_loop(self):
        if self.is_connected and self.current_data["updated"]:
            self.lbl_total_vol.config(text=f"Total Vol: {self.current_data['vol']} V")
            self.lbl_current.config(text=f"Current: {self.current_data['cur']} A")
            self.lbl_soc.config(text=f"SOC: {self.current_data['soc']} %")
            
            current_time = datetime.now().strftime("%H:%M:%S")
            self.time_data.append(current_time)
            self.vol_data.append(self.current_data["vol"])
            self.cur_data.append(self.current_data["cur"])

            self.ax_vol.clear()
            self.ax_cur.clear()
            
            self.ax_vol.plot(self.time_data, self.vol_data, color='blue', marker='o', markersize=3)
            self.ax_vol.set_title("Biến thiên Điện Áp Tổng (V)", fontsize=10)
            self.ax_vol.grid(True, linestyle='--', alpha=0.6)
            
            self.ax_cur.plot(self.time_data, self.cur_data, color='red', marker='o', markersize=3)
            self.ax_cur.set_title("Biến thiên Dòng Điện (A)", fontsize=10)
            self.ax_cur.grid(True, linestyle='--', alpha=0.6)

            self.ax_vol.set_xticks(range(0, len(self.time_data), max(1, len(self.time_data)//4)))
            self.ax_cur.set_xticks(range(0, len(self.time_data), max(1, len(self.time_data)//4)))
            
            self.canvas_left.draw()

            self.ax_cells.clear()
            cell_labels = [f"{i+1}" for i in range(16)]
            cell_voltages = self.current_data["cells"]
            
            # Khởi tạo vẽ 16 cột với màu xanh lá mặc định
            bars = self.ax_cells.bar(cell_labels, cell_voltages, color='mediumseagreen', edgecolor='black')
            self.ax_cells.set_title("Điện áp 16 Cell (V)", fontsize=11, fontweight='bold')
            self.ax_cells.set_xlabel("Cell Number")
            self.ax_cells.grid(True, axis='y', linestyle='--', alpha=0.6)
            
            valid_v = [v for v in cell_voltages if v > 0]
            if valid_v:
                min_v = min(valid_v)
                max_v = max(valid_v)
                ymin = min_v - 0.02 
                ymax = max_v + 0.05
                self.ax_cells.set_ylim([max(0, ymin), ymax])
                
                # Logic đổi màu cho cell cao nhất và thấp nhất
                if min_v != max_v:
                    for bar, val in zip(bars, cell_voltages):
                        if val == min_v:
                            bar.set_facecolor('#ff3333')  # Màu Đỏ cho cell thấp nhất
                        elif val == max_v:
                            bar.set_facecolor('#ffde24')  # Màu Vàng sáng cho cell cao nhất
            else:
                self.ax_cells.set_ylim([0, 5])

            for bar in bars:
                height = bar.get_height()
                self.ax_cells.annotate(f'{height:.3f}',
                                       xy=(bar.get_x() + bar.get_width() / 2, height),
                                       xytext=(0, 3), 
                                       textcoords="offset points",
                                       ha='center', va='bottom', fontsize=8, rotation=90)

            self.canvas_right.draw()

            if self.is_logging:
                with open(self.csv_file, mode='a', newline='') as file:
                    writer = csv.writer(file)
                    row_data = [current_time, self.current_data["vol"], self.current_data["cur"], self.current_data["soc"]] + self.current_data["cells"]
                    writer.writerow(row_data)

            self.current_data["updated"] = False

        self.root.after(1000, self.update_gui_loop)

    def on_closing(self):
        self.is_running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        self.root.quit()

if __name__ == "__main__":
    root = tk.Tk()
    app = BMSDashboardPRO(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()