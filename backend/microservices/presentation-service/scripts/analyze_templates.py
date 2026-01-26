#!/usr/bin/env python3
"""
Analyze Template Structure

Inspects .pptx template files to understand:
- Slide structure vs Layout structure
- Shape types and content
- How to properly preserve design when modifying slides
"""

import os
import sys
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE


def analyze_template(filepath: str):
    """Analyze a single template file."""
    print(f"\n{'='*80}")
    print(f"TEMPLATE: {os.path.basename(filepath)}")
    print(f"{'='*80}")

    prs = Presentation(filepath)

    print(f"\nSlide dimensions: {prs.slide_width.inches:.2f}\" x {prs.slide_height.inches:.2f}\"")
    print(f"Number of slides: {len(prs.slides)}")
    print(f"Number of slide layouts: {len(prs.slide_layouts)}")

    # Analyze slide layouts (from slide master)
    print(f"\n--- SLIDE LAYOUTS (Master) ---")
    for idx, layout in enumerate(prs.slide_layouts):
        placeholder_count = len(list(layout.placeholders))
        shape_count = len(layout.shapes)
        print(f"  Layout [{idx}]: '{layout.name}' - {placeholder_count} placeholders, {shape_count} shapes")

    # Analyze actual slides (the designed content)
    print(f"\n--- ACTUAL SLIDES (Designed Content) ---")
    for slide_idx, slide in enumerate(prs.slides):
        print(f"\n  SLIDE {slide_idx + 1}:")
        print(f"    Layout used: '{slide.slide_layout.name}'")
        print(f"    Total shapes: {len(slide.shapes)}")

        # Categorize shapes
        text_shapes = []
        image_shapes = []
        auto_shapes = []
        other_shapes = []

        for shape in slide.shapes:
            shape_info = {
                "name": shape.name,
                "type": shape.shape_type,
                "left": shape.left.inches if shape.left else 0,
                "top": shape.top.inches if shape.top else 0,
                "width": shape.width.inches if shape.width else 0,
                "height": shape.height.inches if shape.height else 0,
            }

            if shape.has_text_frame:
                text = shape.text_frame.text[:50] + "..." if len(shape.text_frame.text) > 50 else shape.text_frame.text
                shape_info["text"] = text.replace("\n", " | ")
                text_shapes.append(shape_info)
            elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                image_shapes.append(shape_info)
            elif shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
                auto_shapes.append(shape_info)
            else:
                other_shapes.append(shape_info)

        print(f"    Text shapes: {len(text_shapes)}")
        for ts in text_shapes:
            print(f"      - '{ts['name']}' @ ({ts['left']:.1f}, {ts['top']:.1f}) {ts['width']:.1f}x{ts['height']:.1f}")
            print(f"        Text: \"{ts['text']}\"")

        print(f"    Auto shapes (backgrounds, lines): {len(auto_shapes)}")
        for ats in auto_shapes[:5]:  # Show first 5
            print(f"      - '{ats['name']}' @ ({ats['left']:.1f}, {ats['top']:.1f}) {ats['width']:.1f}x{ats['height']:.1f}")
        if len(auto_shapes) > 5:
            print(f"      ... and {len(auto_shapes) - 5} more")

        print(f"    Images: {len(image_shapes)}")
        print(f"    Other: {len(other_shapes)}")

    # Analyze if layouts have actual design or are empty
    print(f"\n--- LAYOUT ANALYSIS ---")
    for idx, layout in enumerate(prs.slide_layouts):
        has_background = False
        has_shapes_with_fill = 0

        for shape in layout.shapes:
            if hasattr(shape, 'fill') and shape.fill:
                try:
                    if shape.fill.type is not None:
                        has_shapes_with_fill += 1
                except:
                    pass

        conclusion = "HAS DESIGN" if has_shapes_with_fill > 0 else "EMPTY (no visual elements)"
        print(f"  Layout [{idx}] '{layout.name}': {has_shapes_with_fill} shapes with fill → {conclusion}")

    print(f"\n{'='*80}")
    print("CONCLUSION:")
    if len(prs.slides) > 0:
        avg_shapes = sum(len(s.shapes) for s in prs.slides) / len(prs.slides)
        print(f"  - Slides have an average of {avg_shapes:.0f} shapes (RICH DESIGN)")
        print(f"  - Layouts may be empty (design is on SLIDES, not in master)")
        print(f"  - Strategy: DUPLICATE slides, not add from layouts")
    else:
        print(f"  - No slides found, using layouts only")


def main():
    """Analyze all templates in the templates directory."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(script_dir, "..", "templates")

    if not os.path.exists(templates_dir):
        print(f"Templates directory not found: {templates_dir}")
        sys.exit(1)

    templates = [f for f in os.listdir(templates_dir) if f.endswith('.pptx')]

    if not templates:
        print(f"No .pptx files found in {templates_dir}")
        sys.exit(1)

    print(f"Found {len(templates)} templates to analyze...")

    for template_file in sorted(templates):
        filepath = os.path.join(templates_dir, template_file)
        try:
            analyze_template(filepath)
        except Exception as e:
            print(f"ERROR analyzing {template_file}: {e}")


if __name__ == "__main__":
    main()
