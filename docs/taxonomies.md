# Taxonomies

Single source of truth for content tags. `build.py` validates every tag in
frontmatter against this file and fails the build on unknown values.

Conventions: lowercase, hyphen-separated, singular, no synonyms, no version
numbers in tag names. To add a tag: add it here first, then use it.

## discipline — exactly one per item, controlled, kept small

- robotics
- automation
- manufacturing
- writing

## tech — many per item, grows freely

- ros2
- moveit2
- opencv
- raspberry-pi
- plc
- scada
- python
- cpp
- javascript
- freecad
- blender
- 3d-printing
- cnc
- arduino
- esp32
