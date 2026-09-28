from tkinter import Tk, font
from tkinter.filedialog import askdirectory, askopenfilename, askopenfilenames
import eel
import sys, os
import shutil
import subprocess
import threading
import time
import json
from json_minify import json_minify
import re
import win32api
import base64
import requests
from subtitles import *

CONSOLE_DEBUG_MODE = False
__version__ = '0.10.1'

# ---- Required Functions ----

def resource_path(relative_path=""):
	""" Get absolute path to resource, works for dev and for PyInstaller """
	base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
	return os.path.join(base_path, relative_path)

@eel.expose
def get_version():
	return __version__

# ---- Locales ----

remove_coma_regex = r'''(?<=[}\]"']),(?!\s*[{["'])'''

@eel.expose
def get_translation(code):
	tr_file = os.path.join(resource_path("web"), "locales", code + ".json")
	if os.path.exists(tr_file):
		with open(tr_file, 'r', encoding="utf-8-sig") as file:
			string = json_minify(file.read()) # remove comments
			string = re.sub(remove_coma_regex, "", string, 0) # remove coma at the end
			output = json.loads(string)
			return output

def load_subs_preview_text():
	file = os.path.join(resource_path("web"), "locales", "subtitles_preview.json")
	with open(file, 'r', encoding="utf-8-sig") as f:
		string = re.sub(remove_coma_regex, "", f.read(), 0)
		data = json.loads(string)
	def wraper(lang): return data.get(lang, data.get('en'))
	return wraper

SUBTITLES_PREVIEW_TEXT = load_subs_preview_text()


# ---- EXE Functions ----

def find_script(script_name):
	def find_in(folder):
		files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
		if script_name in files:
			return os.path.join(folder, script_name)
	
	result = find_in(os.getcwd())
	if result: return result

	result = find_in(resource_path())
	if result: return result

def file_in_temp(file):
	return os.path.dirname(file) == os.path.dirname(resource_path(os.path.basename(file)))


# ---- Settings Functions ----

def load_settings_inline():
	global SCRIPT_FILE, OUTPUT_F, FFMPEG, SUBTITLES_F
	set_file = os.path.join(os.getcwd(), "UI-settings.json")
	settings = {}
	if os.path.exists(set_file):
		with open(set_file, 'r', encoding='utf-8') as file:
			settings = json.loads(file.read())
			if "script_file" in settings.keys():
				SCRIPT_FILE = settings["script_file"]
			if "output_folder" in settings.keys():
				OUTPUT_F = settings["output_folder"]
			if "FFMPEG" in settings.keys():
				FFMPEG = settings["FFMPEG"]
			if "subtitles_folder" in settings.keys():
				SUBTITLES_F = settings["subtitles_folder"]

	SCRIPT_FILE = settings.get("script_file") or find_script("GICutscenes.exe")
	OUTPUT_F = settings.get("output_folder") or os.path.join(os.getcwd(), "output")
	FFMPEG = settings.get("FFMPEG") or find_script("ffmpeg.exe") or "ffmpeg"
	SUBTITLES_F = settings.get("subtitles_folder") or ""

	if os.path.exists(os.path.join(os.getcwd(), "versions.json")) and file_in_temp(SCRIPT_FILE):
		local_ver_file = os.path.join(os.getcwd(), "versions.json")
		temp_ver_file = os.path.join(os.path.dirname(SCRIPT_FILE), "versions.json")
		with open(local_ver_file, 'r') as orig_file:
			data = orig_file.read()
		with open(temp_ver_file, 'w') as temp_file:
			temp_file.write(data)

load_settings_inline()

@eel.expose
def load_settings():
	set_file = os.path.join(os.getcwd(), "UI-settings.json")
	if os.path.exists(set_file):
		with open(set_file, 'r', encoding='utf-8') as file:
			settings = json.loads(file.read())
			return settings
	return {}

@eel.expose
def save_settings(settings):
	settings['output_folder'] = OUTPUT_F
	settings['subtitles_folder'] = SUBTITLES_F
	if not file_in_temp(SCRIPT_FILE):
		settings['script_file'] = SCRIPT_FILE
	if not file_in_temp(FFMPEG):
		settings['FFMPEG'] = FFMPEG

	with open(os.path.join(os.getcwd(), "UI-settings.json"), 'w', encoding='utf-8') as file:
		file.write(json.dumps(settings, indent=4, ensure_ascii=False))
	return True

@eel.expose
def delete_settings():
	global SCRIPT_FILE, OUTPUT_F, FFMPEG, SUBTITLES_F
	SCRIPT_FILE = find_script("GICutscenes.exe")
	OUTPUT_F = os.path.join(os.getcwd(), "output")
	FFMPEG = find_script("ffmpeg.exe") or "ffmpeg"
	SUBTITLES_F = ""
	
	set_file = os.path.join(os.getcwd(), "UI-settings.json")
	if os.path.exists(set_file):
		os.remove(set_file)
		return True
	return False



# ---- About Tab Functions ----

@eel.expose
def get_GICutscenes_ver():
	if SCRIPT_FILE:
		process = subprocess.Popen([SCRIPT_FILE, "--version"], stdout=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
		answer = process.communicate()[0]
		try:
			text = answer.decode('utf-8')
		except UnicodeDecodeError:
			text = answer.decode(os.device_encoding(0))
		return text.strip()

def get_ffmpeg_output(cmd):
	process = subprocess.Popen([
		FFMPEG, "-hide_banner"] + cmd,
		stdout=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW
	)
	answer = process.communicate()[0]
	try:
		text = answer.decode('utf-8')
	except UnicodeDecodeError:
		text = answer.decode(os.device_encoding(0))
	return text

@eel.expose
def get_ffmpeg_ver():
	def find_ver(text):
		return text.splitlines()[0].split("ffmpeg version")[-1].strip().split()[0]
	def find_year(text):
		match = re.findall(r'\b([1-3][0-9]{3})\b', text)
		if match is not None:
			return match
	try:
		text = get_ffmpeg_output(['-version'])
		final = {'ver': find_ver(text.strip()), 'year': find_year(text.strip())}
		return final
	except: return {}


def parse_releases(relative_path):
	r = requests.get(f'https://api.github.com/repos/{relative_path}/tags')
	if r.status_code == 200:
		answer = r.json()
		latest = answer[0]["name"]
		return latest
	else:
		r = requests.get(f'https://github.com/{relative_path}/tags')
		links = []
		for line in r.text.split("\n"):
			match = re.search(r"href=\"(.+)\">", line)
			if match:
				links.append(match.group(1))

		pat = re.compile(r'releases\/tag')
		content = [ s for s in links if pat.findall(s) ]
		latest = sorted(content)[-1].split("/")[-1]
		return latest

@eel.expose
def get_latest_ui_version():
	return parse_releases('SuperZombi/GICutscenesUI')

@eel.expose
def get_latest_script_version():
	return parse_releases('ToaHartor/GI-cutscenes')

@eel.expose
def compare_version_files():
	if SCRIPT_FILE:
		local_ver_file = os.path.join(
			os.path.dirname(SCRIPT_FILE),
			"versions.json"
		)
		if os.path.exists(local_ver_file):
			with open(local_ver_file, 'r') as file:
				LOCAL = file.read()

			try:
				r = requests.get("https://raw.githubusercontent.com/ToaHartor/GI-cutscenes/main/versions.json")
				GLOBAL = r.text

				if json.loads(LOCAL) == json.loads(GLOBAL):
					return {"success": True, "status": True}
				else:
					return {"success": True, "status": False}
			except: None
	return {"success": False}

@eel.expose
def download_latest_version_file():
	r = requests.get("https://raw.githubusercontent.com/ToaHartor/GI-cutscenes/main/versions.json")
	local_ver_file = os.path.join(os.path.dirname(SCRIPT_FILE), "versions.json")
	with open(local_ver_file, 'w') as file:
		file.write(r.text)

	if file_in_temp(SCRIPT_FILE):
		local_ver_file = os.path.join(os.getcwd(), "versions.json")
		with open(local_ver_file, 'w') as file:
			file.write(r.text)


# ---- Logger Functions ----

def send_message_to_ui_output(type_, message):
	eel.putMessageInOutput(type_, message)()

def run_command(command, output_file=None):
	if CONSOLE_DEBUG_MODE:
		return subprocess.call(command)
	process = subprocess.Popen(command, encoding='utf-8', universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)

	def reader(pipe):
		buffer = ""
		try:
			while True:
				chunk = pipe.read(4096)
				if not chunk:
					break
				buffer += chunk
				parts = re.split(r'[\r\n]', buffer)
				buffer = parts.pop()
				for line in parts:
					if line.strip():
						send_message_to_ui_output("console", line.strip())
		except (OSError, ValueError):
			pass
		if buffer.strip():
			send_message_to_ui_output("console", buffer.strip())
		try:
			pipe.close()
		except (OSError, ValueError):
			pass

	threading.Thread(target=reader, args=(process.stderr,), daemon=True).start()
	threading.Thread(target=reader, args=(process.stdout,), daemon=True).start()

	last_size = -1
	frozen_for = 0.0
	start = time.time()
	while True:
		try:
			return process.wait(timeout=0.25)
		except subprocess.TimeoutExpired:
			pass
		if STOPED_BY_USER:
			process.kill()
			continue
		if output_file:
			try:
				size = os.path.getsize(output_file)
			except OSError:
				size = 0
			frozen_for = frozen_for + 0.25 if size == last_size else 0
			last_size = size
			if time.time() - start > 10 and frozen_for >= 5:
				send_message_to_ui_output("console", "ffmpeg output has not changed for 5s, assuming it is frozen and stopping")
				process.kill()
				continue


def get_encoder_chain(selection):
	"""Encoders to try in order; on failure the next one is used."""
	chain = []
	if selection and selection != "auto":
		chain.append(selection)
	else:
		for gpu in GPU_args:
			encoder = GPU_args[gpu]["encode"]
			if test_encoder(encoder):
				chain.append(encoder)
	chain += ["libx264", "h264_mf", "libsvtav1", "libaom-av1"]
	return chain


# ---- Explorer Functions ----

def get_disks():
	return [d for d in win32api.GetLogicalDriveStrings()[0]]

@eel.expose
def get_all_fonts():
	root = Tk()
	root.withdraw()
	return sorted(set(font.families()))

@eel.expose
def ask_files():
	root = Tk()
	root.withdraw()
	root.wm_attributes('-topmost', 1)
	files = askopenfilenames(initialdir=GENSHIN_FOLDER, parent=root,
		filetypes=[("Genshin Impact Cutscene", "*.usm"), ("All files", "*.*")]
	)
	return files

def ask_folder():
	root = Tk()
	root.withdraw()
	root.wm_attributes('-topmost', 1)
	return askdirectory(parent=root)

@eel.expose
def get_output_folder():
	return OUTPUT_F

@eel.expose
def get_subtitles_folder():
	return SUBTITLES_F

@eel.expose
def ask_output_folder():
	global OUTPUT_F
	folder = ask_folder()
	if folder: OUTPUT_F = folder
	return OUTPUT_F

@eel.expose
def ask_subtitles_folder():
	global SUBTITLES_F
	folder = ask_folder()
	if folder: SUBTITLES_F = folder
	return SUBTITLES_F

@eel.expose
def open_output_folder():
	if os.name == "nt":
		subprocess.run(['explorer', OUTPUT_F], creationflags=subprocess.CREATE_NO_WINDOW)
	elif os.name == "posix":
		subprocess.run(['xdg-open', OUTPUT_F], creationflags=subprocess.CREATE_NO_WINDOW)

def find_genshin_folder():
	if os.name == "nt":
		templates = (
			('Games', 'Genshin Impact'),
			('Program Files', 'Genshin Impact'),
			('Program Files', 'HoYoPlay', 'games')
		)
		for _disk in get_disks():
			disk = f'{_disk}:'+os.sep
			for template in templates:
				path = os.path.join(disk, *template)
				if os.path.exists(path):
					assets = os.path.join(path, "Genshin Impact game", "GenshinImpact_Data", "StreamingAssets", "VideoAssets", "StandaloneWindows64")
					if os.path.exists(assets): return assets
	print("[WARN] Assets not found!")
GENSHIN_FOLDER = find_genshin_folder()


# ---- Subtitles Functions ----
@eel.expose
def make_subs_preview(args):
	params = {
		"tempfile": "temp.ass",
		"width": 1920, "height": 1080,
		**args
	}
	width, height, tempfile = params.pop("width"), params.pop("height"), params.pop("tempfile")
	make_subs_template(text=SUBTITLES_PREVIEW_TEXT(params.pop("lang")), file=tempfile, **params)
	cmd = [
		FFMPEG, '-f', 'lavfi', '-i', 
		f'color=color=black@0.0:size={width}x{height},format=rgba,subtitles={tempfile}:alpha=1', 
		'-vframes', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'
	]
	process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
	output, error = process.communicate()
	os.remove(tempfile)
	if process.returncode == 0:
		img_base64 = base64.b64encode(output).decode('utf-8')
		data_url = f"data:image/png;base64,{img_base64}"
		return data_url


# ---- GPU Functions ----
GPU_args = {
	"nvidia": {
		"decode": 'cuda',
		"encode": 'h264_nvenc'
	},
	"intel": {
		"decode": 'qsv',
		"encode": 'h264_qsv'
	},
	"amd": {
		"encode": "h264_amf"
	}
}
def test_encoder(encoder, decoder=None):
	try:
		cmd = [
			FFMPEG, '-f', 'lavfi', '-i', 
			'color=black:size=360x360', 
			'-vframes', '1', '-f', "null",
			'-vcodec', encoder, '-'
		]
		process = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
		returncode = process.wait()
		if returncode == 0: return True
	except: None


# ---- MAIN Functions ----
STOPED_BY_USER = None
@eel.expose
def stop_work():
	global STOPED_BY_USER
	STOPED_BY_USER = True

@eel.expose
def start_work(files, args):
	global STOPED_BY_USER
	STOPED_BY_USER = False
	send_message_to_ui_output("event", "start")
	file_lenth = len(files)
	send_message_to_ui_output("file_count", [0, file_lenth])
	# Make folders
	temp_folder = resource_path("Temp")
	if not os.path.exists(temp_folder):
		os.mkdir(temp_folder)
	if not os.path.exists(OUTPUT_F):
		os.mkdir(OUTPUT_F)

	OLD_DIR = os.getcwd()
	os.chdir(os.path.dirname(SCRIPT_FILE))

	for i, file in enumerate(files):
		if STOPED_BY_USER: break
		else:
			send_message_to_ui_output("file_count", [i, file_lenth])
			send_message_to_ui_output("event", "copy_files")
			send_message_to_ui_output("work_file", file)
			send_message_to_ui_output("console", f"----- {os.path.basename(file)} -----")
			send_message_to_ui_output("event", "run_demux")
			# MAIN CALL
			p_status = 0
			if CONSOLE_DEBUG_MODE:
				subprocess.call([SCRIPT_FILE, 'demuxUsm', file, '--output', OUTPUT_F])
			else:
				p_status = run_command([SCRIPT_FILE, 'demuxUsm', file, '--output', OUTPUT_F])

			if p_status != 0:
				send_message_to_ui_output("event", "error")
				send_message_to_ui_output("sub_work", {"name": "keys", "status": False})
			else:
				send_message_to_ui_output("event", "rename_files")

				# Rename to m2v
				old_file_name = os.path.splitext(os.path.basename(file))[0]
				file_name = str(old_file_name) + ".ivf"
				new_file_name = str(old_file_name) + ".m2v"
				file_name = os.path.join(OUTPUT_F, file_name)
				new_file_name = os.path.join(OUTPUT_F, new_file_name)
				if os.path.exists(file_name):
					if os.path.exists(new_file_name): os.remove(new_file_name)
					os.rename(file_name, new_file_name)
				else:
					send_message_to_ui_output("console", "\n")
					send_message_to_ui_output("event", "error")
					send_message_to_ui_output("sub_work", {"name": "keys", "status": False})
					continue

				# Delete hca encoded Audio (cuz wav files decoded)
				for index in [0, 1, 2, 3]:
					f = str(old_file_name) + "_" + str(index) + ".hca"
					f = os.path.join(OUTPUT_F, f)
					if os.path.exists(f):
						os.remove(f)

				# Merge / Convert
				if STOPED_BY_USER: break
				audio_index = int(args['audio_index']) if args['merge'] else 0
				audio_file = os.path.join(OUTPUT_F, str(old_file_name) + "_" + str(audio_index) + ".wav")
				webm_file = os.path.join(OUTPUT_F, str(old_file_name) + ".webm")
				mp4_file = os.path.join(OUTPUT_F, str(old_file_name) + ".mp4")

				# Subtitles
				subtitles_file = None
				subtitles = None
				if args['subtitles']:
					send_message_to_ui_output("console", "\nSearching for subtitles")

					if args.get('subtitles_provider') == "local":
						if args.get('subtitles_folder'):
							subtitles = find_subtitles(
								old_file_name,
								provider=args.get('subtitles_folder'),
								lang=args.get('subtitles_lang')
							)
					elif args.get('subtitles_provider') == "url":
						if args.get('subtitles_url'):
							subtitles = find_subtitles(
								old_file_name,
								provider=args.get('subtitles_url'),
								lang=args.get('subtitles_lang')
							)
					else:
						subtitles = find_subtitles(
							old_file_name,
							provider=args.get('subtitles_provider'),
							lang=args.get('subtitles_lang')
						)

					if not subtitles:
						send_message_to_ui_output("console", "Subtitles not found!")
						send_message_to_ui_output("sub_work", {"name": "subtitles", "status": False})
					else:
						stream_subs = args.get('subtitles_mode') == "stream"
						if not args.get('convert_mp4'):
							send_message_to_ui_output("console", "Subtitles only apply to MP4 output")
						send_message_to_ui_output("console", "Converting subtitles")
						send_message_to_ui_output("sub_work", {"name": "subtitles", "status": True})
						if stream_subs:
							subtitles_file = os.path.join(temp_folder, str(old_file_name) + ".srt")
							with open(subtitles_file, 'w', encoding='utf-8') as f:
								f.write(subtitles.read())
						else:
							subtitles_file = os.path.join(temp_folder, str(old_file_name) + ".ass")
							srt_to_ass(
								subtitles,
								subtitles_file,
								font_name=args.get('subtitles_font'),
								font_size=args.get('subtitles_fontsize'),
								text_color=args.get('subtitles_text_color'),
								outline_color=args.get('subtitles_outline_color'),
								outline_width=args.get('subtitles_outline_width'),
								letter_spacing=args.get('subtitles_letter_spacing'),
								bold=args.get('subtitles_bold'),
								italic=args.get('subtitles_italic')
							)

				# Remux video to webm
				send_message_to_ui_output("event", "run_merge")
				send_message_to_ui_output("console", "\nStarting ffmpeg...")
				if os.path.exists(webm_file):
					send_message_to_ui_output("console", f'File {webm_file} already exists.')
					os.remove(webm_file)
				command = [FFMPEG, '-hide_banner', '-i', new_file_name]
				if args['merge']:
					send_message_to_ui_output("console", "Merging audio into webm")
					command += ['-i', audio_file]
				command += ['-c:v', 'copy']
				if args['merge']:
					command += ['-c:a', 'libopus', '-b:a', '320K']
				send_message_to_ui_output("console", "Working ffmpeg...")
				p_status = run_command(command + [webm_file])
				if p_status != 0:
					if os.path.exists(webm_file): os.remove(webm_file)
					send_message_to_ui_output("event", "error")
					continue
				send_message_to_ui_output("console", "webm created!")

				# Convert to MP4
				if args.get('convert_mp4'):
					send_message_to_ui_output("console", "\nConverting to MP4")
					if os.path.exists(mp4_file):
						send_message_to_ui_output("console", f'File {mp4_file} already exists.')
						os.remove(mp4_file)
					subtitles_args = []
					stream_subs = bool(subtitles_file and args.get('subtitles_mode') == "stream")
					if subtitles_file and not stream_subs:
						subs_file = os.path.relpath(subtitles_file).replace("\\", "/")
						subtitles_args = ["-vf", f'subtitles={subs_file}']
					audio_strategies = [[]]
					mapping_args = ['-map', '0:v:0']
					bitrate_args = []
					if args.get('mp4_bitrate'):
						bitrate_args = ['-b:v', str(int(args['mp4_bitrate'])) + 'K']
					if args['merge']:
						if args.get('lossless_audio'):
							# Lossless: copy PCM from the wav into the mp4 (ipcm)
							audio_strategies = [
								['-i', audio_file, '-c:a', 'copy', '-map', '1:a:0'],
								['-i', audio_file, '-c:a', 'aac', '-b:a', '320K', '-map', '1:a:0']
							]
						else:
							# Default: reuse the opus track from the webm
							audio_strategies = [
								['-map', '0:a:0', '-c:a', 'copy'],
								['-i', audio_file, '-c:a', 'aac', '-b:a', '320K', '-map', '1:a:0']
							]

					p_status = 1
					encoder_chain = get_encoder_chain(args.get('mp4_encoder'))
					for audio_args in audio_strategies:
						if 'aac' in audio_args:
							send_message_to_ui_output("console", "Audio copy not supported, re-encoding audio to AAC")
						audio_input = audio_args[:2] if audio_args[:1] == ['-i'] else []
						audio_output = audio_args[2:] if audio_input else audio_args
						for index, encoder in enumerate(encoder_chain):
							if STOPED_BY_USER: break
							if os.path.exists(mp4_file): os.remove(mp4_file)
							send_message_to_ui_output("console", f'Encoding with {encoder}...')
							srt_input = ['-i', subtitles_file] if stream_subs else []
							subs_map_args = ['-map', f"{2 if audio_input else 1}:s:0", '-c:s', 'mov_text'] if stream_subs else []
							command = [FFMPEG, '-hide_banner', '-i', webm_file] + audio_input + srt_input + mapping_args + subtitles_args + ['-c:v', encoder] + audio_output + subs_map_args + bitrate_args + [mp4_file]
							p_status = run_command(command, mp4_file)
							if p_status == 0: break
							if index + 1 < len(encoder_chain):
								send_message_to_ui_output("console", f'Encoder {encoder} failed, retrying with {encoder_chain[index + 1]}...')
							else:
								send_message_to_ui_output("console", f'Encoder {encoder} failed.')
						if p_status == 0: break
					if p_status != 0:
						if os.path.exists(mp4_file): os.remove(mp4_file)
						send_message_to_ui_output("event", "error")
						continue
					send_message_to_ui_output("console", "MP4 created!")

				# Cleanup
				if args['delete_after_merge'] and (args['merge'] or args.get('convert_mp4')):
					send_message_to_ui_output("console", "Removing trash...")
					files_to_remove = [new_file_name]
					if args['merge']:
						files_to_remove += [os.path.join(OUTPUT_F, f"{old_file_name}_{i}.wav") for i in [0, 1, 2, 3]]
					if args.get('convert_mp4'):
						files_to_remove += [webm_file]
					if subtitles_file:
						files_to_remove += [subtitles_file]
					for f in files_to_remove:
						if os.path.exists(f): os.remove(f)
					send_message_to_ui_output("console", "OK")

				if i != file_lenth - 1:
					send_message_to_ui_output("console", "\n")

				send_message_to_ui_output("event", "ok")

	send_message_to_ui_output("event", "finish")
	if STOPED_BY_USER:
		send_message_to_ui_output("console", "\nStoped by user")
		send_message_to_ui_output("event", "stoped")
	else:
		send_message_to_ui_output("file_count", [file_lenth, file_lenth])
	shutil.rmtree(temp_folder)
	os.chdir(OLD_DIR)


eel.init(resource_path("web"))

browsers = ['chrome', 'default']
for browser in browsers:
	try:
		eel.start("main.html", size=(600, 800), mode=browser, port=0)
		break
	except Exception:
		print(f"Failed to launch the app using {browser.title()} browser")
