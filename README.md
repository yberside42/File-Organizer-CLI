## File Organizer CLI

Command-Line tool that scan, classify and organize files into category folders witha a preview / run / undo workflow. This tool has duplicate / collision policias and a merge command to consolidate directories. Built in Python. 

--- 

## Technologies & Requirements
- Python 3.10
- Standard libraries: argparse, logging, pathlib, shutil, hashlib, json, etc.

## Features

- Preview: Generates an organization plan for the user to review. (No changes made).
- Run: This command apply the preview with: 
    - Filters: Extensions, minimum size / maximum size, supports KB/MB/GB/TB.
    - Categories: extension -> category.
    - Dates: Optional partition by date using created and modified time.
    - Collision policy: The tool ask if you want to rename / keep-newest / skip if a collision happens.
    - Duplicate policy: Consolidate files applying the same policies.
    - History: Each run and merge stores a batch that contains plan, stats and metadata. 

## Structure

- organizer.py: Entry point and dispatcher.
- cli.py: Argparse parser and subcommands.
- planner.py: Plan builder, collision and duplicate policies, plan renderer and filters.
- history.py: history.json read and write, batch IDs, appends and get last.
- file_utils.py: Execute moves and policies.
- config_loader.py: load_config(path) with sane defaults + normalization.
- logger.py: Setup logger; rotating file and console.
- config.json: categories and behavior. 

## Configuration

The files are classified by extension into categories, if the file is unmatched it goes to an "other" bucket.

Formats supported: 
- media: "jpg","jpeg","png","gif","webp","svg","heic","mp4", "mkv","avi","mov","mp3","wav","flac","m4a".

- docs: "pdf","doc","docx","xls","xlsx","ppt","pptx","txt","md","rtf","csv".

"code": "py","js","ts","html","css","json","yml","yaml","sql","sh","bat","ps1".

- archives:"zip","rar","7z","tar","gz","bz2".

- executables: "exe","msi","dmg","app","bin".

---

## Usage

Run the CLI as a module from the project folder:

```bash
cd file_organizer
python -m file_organizer.cli --help
```
Use --debug for verbose logs.
Use --history to set a custom path to history.json.

- Preview a plan: 

python -m file_organizer.organizer preview \
  --path /path/to/folder \
  --only-ext .jpg,.png,.pdf \
  --size-min 100KB --size-max 2GB \
  --by-date modified \
  --collision rename \
  --dedupe skip \
  --dry-run --debug

- Run (apply changes):

python -m file_organizer.organizer run \
  --path /path/to/folder \
  --only-ext .jpg,.png \
  --by-date created \
  --collision keep-newest \
  --dedupe skip \
  --history /path/to/history.json

- Undo last Run:

python -m file_organizer.organizer undo -y --history /path/to/history.json

- Merge directories (src -> dest)

python -m file_organizer.organizer merge \
  --src /path/A \
  --dest /path/B \
  --only-ext .pdf,.docx \
  --collision rename \
  --dedupe skip \
  -y

- Validate config
python -m file_organizer.organizer validate-config

## How it works

- Discover files in the target folder.
- Filter the extensions and / or size.
- Build the plan.
- Apply any collision policy and dedupe policy.
- Render the plan (table) and a summary (by category).
- Run executes the plan, it moves and appends a batch to history.json.
- Undo replays the move in reverse. 

---

## Learned:
- Learned to work with file systems using Pathlib and shutil.
- Learned to implement collision and dedupe policies.
- Learned a new work flow. 
- Improved my management of dynamic configurations with JSON.
- Learned to use logging with file rotation
- Learned to build and structure a more complex CLI application. 

---

## License 
This project is licensed under the [MIT License](LICENSE)
© 2025 Yael Tapia.

