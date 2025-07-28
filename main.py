import fitz  # PyMuPDF
import json
import os
import re
from collections import Counter

class PDFOutlineExtractor:
   

    def __init__(self):
        self.pages_data = [] # Stores extracted text spans with detailed metadata
        self.unique_font_sizes = set()
        self.heading_font_map = {} # Maps font size to a potential heading level (H1, H2, H3)

    def extract_text_elements(self, pdf_path):
       
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"Error opening PDF {pdf_path}: {e}")
            return []

        all_pages_elements = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text_blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_LIGATURES)["blocks"]

            page_elements = []
            for block in text_blocks:
                if block['type'] == 0:  # This is a text block
                    for line in block['lines']:
                        for span in line['spans']:
                            # Round font size for consistent grouping
                            font_size = round(span['size'], 2)
                            self.unique_font_sizes.add(font_size)

                            page_elements.append({
                                "text": span['text'].strip(),
                                "font_size": font_size,
                                "is_bold": "bold" in span['font'].lower() or (span['flags'] & 16), # Bit 4 (0x10) is bold
                                "is_italic": "italic" in span['font'].lower() or (span['flags'] & 2), # Bit 1 (0x02) is italic
                                "bbox": list(fitz.Rect(span['bbox'])), # Convert Rect to list
                                "page": page_num + 1,
                                "line_y0": line['bbox'][1], # y-coordinate of the start of the line
                                "line_y1": line['bbox'][3], # y-coordinate of the end of the line
                                "line_x0": line['bbox'][0], # x-coordinate of the start of the line
                                "line_x1": line['bbox'][2] # x-coordinate of the end of the line
                            })
            all_pages_elements.append(page_elements)
        
        doc.close()
        self.pages_data = all_pages_elements
        return all_pages_elements

    def _determine_heading_font_map(self, exclude_font_size=None):
       
        if not self.unique_font_sizes:
            return

        sorted_font_sizes = sorted(list(self.unique_font_sizes), reverse=True)
        
        significant_font_sizes = [s for s in sorted_font_sizes if s >= 10.0]

        if not significant_font_sizes:
            return

        MIN_H1_H2_DIFF = 2.0  # H1 must be at least 2 points larger than H2
        MIN_H2_H3_DIFF = 1.5  # H2 must be at least 1.5 points larger than H3
        
        h1_fs = None
        h2_fs = None
        h3_fs = None

        self.heading_font_map = {} # Reset map

        for fs in significant_font_sizes:
            if exclude_font_size is not None and abs(fs - exclude_font_size) < 0.1: # Use tolerance for exclusion
                continue

            if h1_fs is None: # First valid significant font size becomes H1 candidate
                h1_fs = fs
                self.heading_font_map[h1_fs] = "H1"
            elif h2_fs is None and (h1_fs - fs) >= MIN_H1_H2_DIFF:
                h2_fs = fs
                self.heading_font_map[h2_fs] = "H2"
            elif h3_fs is None and h2_fs is not None and (h2_fs - fs) >= MIN_H2_H3_DIFF: # Added h2_fs is not None check
                h3_fs = fs
                self.heading_font_map[h3_fs] = "H3"
            
            if h1_fs is not None and h2_fs is not None and h3_fs is not None:
                break
        
       
        if h1_fs is None and significant_font_sizes:
            for fs in significant_font_sizes:
                if exclude_font_size is None or abs(fs - exclude_font_size) >= 0.1:
                    self.heading_font_map[fs] = "H1"
                    h1_fs = fs
                    break # Assign the first one found as H1
        
        if h1_fs is not None and h2_fs is None:
            for fs in significant_font_sizes:
                if fs == h1_fs or (exclude_font_size is not None and abs(fs - exclude_font_size) < 0.1):
                    continue
                if fs < h1_fs:
                    self.heading_font_map[fs] = "H2"
                    h2_fs = fs
                    break
        
        if h2_fs is not None and h3_fs is None:
            for fs in significant_font_sizes:
                if fs == h1_fs or fs == h2_fs or (exclude_font_size is not None and abs(fs - exclude_font_size) < 0.1):
                    continue
                if fs < h2_fs:
                    self.heading_font_map[fs] = "H3"
                    h3_fs = fs
                    break


    def identify_document_title(self):
       
        if not self.pages_data or not self.pages_data[0]:
            return "Untitled Document", None, None

        first_page_elements = self.pages_data[0]
        
        max_font_size = 0
        for element in first_page_elements:
            if element['font_size'] > max_font_size:
                max_font_size = element['font_size']
        
        if max_font_size == 0:
            return "Untitled Document", None, None

        potential_title_elements = []
        for element in first_page_elements:
            if abs(element['font_size'] - max_font_size) < 0.1: 
                potential_title_elements.append(element)
        
        if not potential_title_elements:
            return "Untitled Document", None, None

        potential_title_elements.sort(key=lambda x: x['bbox'][1])

        document_title_lines = []
        last_y_bottom = -1
        title_bbox = None
        
        for element in potential_title_elements:
            if not document_title_lines or (element['bbox'][1] - last_y_bottom < (element['font_size'] * 1.5)):
                document_title_lines.append(element['text'])
                if title_bbox is None:
                    title_bbox = fitz.Rect(element['bbox'])
                else:
                    title_bbox |= fitz.Rect(element['bbox']) # Expand bbox to include all lines
                last_y_bottom = element['bbox'][3]
            else:
                break
        
        final_title_text = " ".join(document_title_lines).strip()
        
        if "author" in final_title_text.lower() or "presented at" in final_title_text.lower() or len(final_title_text.split()) < 3:
             
             pass

        return final_title_text if final_title_text else "Untitled Document", max_font_size, list(title_bbox) if title_bbox else None


    def identify_headings(self):
        
        outline = []
       
        for page_elements in self.pages_data: # pages_data is already filtered for title
            current_line_y0 = -1
            temp_line_spans = []
            
            lines_with_spans = [] 

            if page_elements:
               
                page_bbox = fitz.Rect(page_elements[0]['bbox'])
                for el in page_elements:
                    page_bbox |= fitz.Rect(el['bbox'])
                page_width = page_bbox.width
                page_height = page_bbox.height


                for element in page_elements:
                    text_lower = element['text'].lower()
                    
                    if re.search(r'http[s]?://|www\.|@', text_lower):
                        continue
                    
                   
                    is_top_of_page = element['line_y0'] < (page_height * 0.15) # Top 15% of page
                    is_bottom_of_page = element['line_y1'] > (page_height * 0.85) # Bottom 15% of page

                    if (element['font_size'] < 12 and # Small font size
                        (is_top_of_page or is_bottom_of_page) and # Located at top/bottom
                        (re.search(r'^[a-z]+\.[a-z]+@', text_lower) or # email-like
                         re.search(r'department of|university|institute|college', text_lower) or
                         re.search(r'^[a-z]\.[a-z]\. [a-z]+$', text_lower) or # e.g. H. T. Hà
                         re.search(r'res math sci|journal of|proceedings of|math sci', text_lower) or # Common journal/conf names
                         re.search(r'h\. t\. h[aà], a\. van tuyl', text_lower) # Specific author pattern
                        )):
                        continue
                    
                    if ((re.fullmatch(r'^\s*[\d\s\.\-—–]+\s*$', element['text']) and len(element['text']) < 10) or # Pure numbers/symbols
                        re.fullmatch(r'^\s*page\s+\d+\s+of\s+\d+\s*$', text_lower) or # "Page X of Y"
                        re.fullmatch(r'^\d+\s+page\s+\d+\s+of\s+\d+$', text_lower) or # "22 Page 2 of 26"
                        re.fullmatch(r'^\d+\s*:\s*\d+$', text_lower) or # e.g., "9:22"
                        re.fullmatch(r'^\d+$', element['text'].strip()) # Just a number
                       ) and (is_top_of_page or is_bottom_of_page): # Only filter if at top/bottom of page
                        continue
                    
                    if (element['font_size'] < 14 and len(element['text'].split()) < 5 and
                        element['text'].strip().upper() == "RESEARCH" and is_top_of_page):
                        continue
                    
                   
                    if re.fullmatch(r'^\s*[a-z]\d+:\s*$', text_lower) or \
                       re.fullmatch(r'^\s*[0-9\(\)\.,\-\–:]+\s*$', text_lower) or \
                       re.fullmatch(r'^\s*[a-z]\d+\s*$', text_lower): # e.g. "i2"
                        continue

                        
                    if abs(element['line_y0'] - current_line_y0) > 0.1: # New line detected
                        lines_with_spans.append(temp_line_spans)
                        temp_line_spans = [element]
                        current_line_y0 = element['line_y0']
                    else:
                        temp_line_spans.append(element)
                
                if temp_line_spans: # Add the last line
                    lines_with_spans.append(temp_line_spans)

            for i, line_spans in enumerate(lines_with_spans):
                full_line_text = " ".join([span['text'] for span in line_spans if span['text']]).strip()
                
                if not full_line_text:
                    continue

                line_font_sizes = [span['font_size'] for span in line_spans]
                line_bold_statuses = [span['is_bold'] for span in line_spans]
                line_italic_statuses = [span['is_italic'] for span in line_spans]
                
                most_common_font_size = Counter(line_font_sizes).most_common(1)[0][0] if line_font_sizes else 0
                any_bold_in_line = any(line_bold_statuses)
                any_italic_in_line = any(line_italic_statuses)
                all_spans_bold = all(span['is_bold'] for span in line_spans)
                
                page_num = line_spans[0]['page']
                
                text_to_classify = full_line_text
                level_candidate = None
                is_potential_heading = False

                for mapped_fs, level in self.heading_font_map.items():
                    if abs(most_common_font_size - mapped_fs) <= 1.0:
                        level_candidate = level
                        break
                
                if level_candidate:
                    is_potential_heading = True

                numeric_pattern = re.match(r'^((\d+\.)+\d*|\d+)\s+.*$', text_to_classify)
                alpha_pattern = re.match(r'^[A-Z]\.\s+.*$', text_to_classify)
                bullet_pattern = re.match(r'^[•\*\-]\s*.*$', text_to_classify) # Allow space after bullet

                if numeric_pattern or alpha_pattern:
                    is_potential_heading = True
                    if re.match(r'^((\d+\.)+\d*|\d+|[A-Z])\s*,\s*.*$', text_to_classify): # Ends with comma, likely not heading
                        is_potential_heading = False
                    elif len(text_to_classify.split()) > 20: # Too long for simple numeric heading
                         is_potential_heading = False
                    else: # If still potential, assign level
                        if numeric_pattern:
                            parts = numeric_pattern.group(1).split('.')
                            if len(parts) == 3: level_candidate = "H3"
                            elif len(parts) == 2: level_candidate = "H2"
                            elif len(parts) == 1: level_candidate = "H1"
                        elif alpha_pattern:
                            if not level_candidate or {"H1":1, "H2":2, "H3":3}.get(level_candidate,4) > 1:
                                level_candidate = "H1" 

                if bullet_pattern:
                    is_potential_heading = True
                    if not level_candidate or {"H1":1, "H2":2, "H3":3}.get(level_candidate,4) > 3:
                        level_candidate = "H3"

                bold_prefix_match = False
                
                if len(line_spans) > 0 and line_spans[0]['is_bold']:
                    combined_prefix_text = ""
                    for span_idx, span in enumerate(line_spans):
                        if span['is_bold']:
                            combined_prefix_text += span['text']
                            if combined_prefix_text.strip().endswith(':'):
                                if span_idx + 1 < len(line_spans) and not line_spans[span_idx + 1]['is_bold']:
                                    bold_prefix_match = True
                                    text_to_classify = combined_prefix_text.strip()
                                    if bullet_pattern: # If it also has a bullet, it's a strong H3
                                        level_candidate = "H3"
                                    elif not level_candidate or {"H1":1, "H2":2, "H3":3}.get(level_candidate,4) > 2: # Default to H2 if no stronger level
                                        level_candidate = "H2" # Often bolded prefixes are H2 or H3
                                    is_potential_heading = True
                                    break 
                                elif span_idx + 1 == len(line_spans): # Bold prefix is the entire line and ends with colon
                                    bold_prefix_match = True
                                    text_to_classify = combined_prefix_text.strip()
                                    if bullet_pattern:
                                        level_candidate = "H3"
                                    elif not level_candidate or {"H1":1, "H2":2, "H3":3}.get(level_candidate,4) > 2:
                                        level_candidate = "H2"
                                    is_potential_heading = True
                                    break
                        else:
                            break # Non-bold span means no continuous bold prefix ending in colon

                text_colon_match = False
                if not is_potential_heading: # Only apply if not already classified by stronger rule
                    colon_idx = full_line_text.find(':')
                    if colon_idx != -1:
                        potential_heading_part = full_line_text[:colon_idx].strip()
                        if len(potential_heading_part.split()) < 10 and len(full_line_text) > colon_idx + 1:
                            text_after_colon = full_line_text[colon_idx+1:].strip()
                            if not re.match(r'^((\d+\.)+\d*|\d+|[A-Z]|[•\*\-])\s*.*$', text_after_colon):
                                text_colon_match = True
                                is_potential_heading = True
                                level_candidate = "H3" # Default to H3 for this pattern
                                text_to_classify = potential_heading_part + ":" # Include the colon in the heading text

                keyword_match = False
                if not is_potential_heading: # Only apply if not already classified
                    keyword_patterns = {
                        r'^(theorem|deﬁnition|remark|example|conjecture|lemma|proof)\s+\d+(\.\d+)*\s*.*$': "H3", # e.g., Theorem 2.10
                        r'^(theorem|deﬁnition|remark|example|conjecture|lemma|proof)\s*:\s*.*$': "H3", # e.g., Proof:
                        r'^(theorem|deﬁnition|remark|example|conjecture|lemma|proof)\s*$' : "H3" # e.g., Abstract, Introduction
                    }
                    for pattern, level in keyword_patterns.items():
                        if re.match(pattern, text_lower):
                            if (any_bold_in_line or any_italic_in_line or len(full_line_text.split()) < 15):
                                keyword_match = True
                                is_potential_heading = True
                                level_candidate = level
                                text_to_classify = full_line_text # Keep full text for these
                                break
                
               
                is_short_line = len(text_to_classify.split()) < 15 and len(text_to_classify) < 120 
                ends_with_period = text_to_classify.endswith('.')
                ends_with_colon = text_to_classify.endswith(':') # New check for colon

                if is_potential_heading:
                    if bullet_pattern and level_candidate == "H3":
                        if len(text_to_classify) > 60:
                            is_potential_heading = False
                        
                        if is_potential_heading and i + 1 < len(lines_with_spans):
                            next_line_spans = lines_with_spans[i+1]
                            next_full_line_text = " ".join([s['text'] for s in next_line_spans if s['text']]).strip()
                            next_line_y0 = next_line_spans[0]['line_y0']
                            current_line_y_bottom = line_spans[-1]['bbox'][3] 

                            if (next_line_y0 - current_line_y_bottom < (most_common_font_size * 1.0)) and \
                               not any(s['is_bold'] for s in next_line_spans) and \
                               not re.match(r'^((\d+\.)+\d*|\d+|[A-Z]|[•\*\-])\s*.*$', next_full_line_text):
                                is_potential_heading = False

                    if bold_prefix_match or text_colon_match or keyword_match:
                        pass 
                    else:
                        if not any_bold_in_line and \
                           not (numeric_pattern or alpha_pattern or bullet_pattern) and most_common_font_size < 12:
                            is_potential_heading = False 

                        if is_potential_heading and not ends_with_period:
                            pass # Good sign
                        elif is_potential_heading and ends_with_period: # If it ends with a period
                            if not (numeric_pattern or alpha_pattern):
                                if most_common_font_size < 14 and not any_bold_in_line:
                                    is_potential_heading = False
                
                if not is_potential_heading and any_bold_in_line:
                    if all_spans_bold: # Check if ALL spans are bold
                        if len(full_line_text) < 150 and not full_line_text.endswith('.'):
                            is_potential_heading = True
                            level_candidate = "H3"
                        elif len(full_line_text) < 50 and full_line_text.endswith('.'):
                            is_potential_heading = True
                            level_candidate = "H3"
                    elif not bold_prefix_match: # Already handled bold_prefix_match above
                        
                        first_bold_span_idx = -1
                        for idx, span in enumerate(line_spans):
                            if span['is_bold']:
                                first_bold_span_idx = idx
                                break
                        
                        if first_bold_span_idx == 0: # Bold text starts at the beginning of the line
                            bold_segment_text = ""
                            bold_segment_length = 0
                            span_idx_after_bold = -1
                            for span_idx in range(len(line_spans)):
                                if line_spans[span_idx]['is_bold']:
                                    bold_segment_text += line_spans[span_idx]['text']
                                    bold_segment_length += len(line_spans[span_idx]['text'])
                                else:
                                    span_idx_after_bold = span_idx
                                    break # End of bold segment
                            
                            if bold_segment_length > 0 and \
                               (span_idx_after_bold != -1 and not line_spans[span_idx_after_bold]['is_bold']) and \
                               len(bold_segment_text.split()) < 10 and \
                               (not bold_segment_text.strip().endswith('.') or len(bold_segment_text) < 30): # Allow short bold sentences
                                
                                is_potential_heading = True
                                level_candidate = "H3"
                                text_to_classify = bold_segment_text.strip() # Only the bold part

                if is_potential_heading and level_candidate:
                    outline.append({
                        "level": level_candidate,
                        "text": text_to_classify,
                        "page": page_num
                    })
        
        final_outline = []
        last_entry_text = ""
        last_entry_page = -1
        last_entry_level_rank = 0

        for entry in outline:
            current_entry_level_rank = {"H1": 1, "H2": 2, "H3": 3}.get(entry['level'], 4)

            if entry['text'] == last_entry_text and entry['page'] == last_entry_page:
                continue

            if final_outline:
                prev_entry = final_outline[-1]
                prev_level_rank = {"H1": 1, "H2": 2, "H3": 3}.get(prev_entry['level'], 4)

                if entry['page'] == prev_entry['page'] and current_entry_level_rank < prev_level_rank:
                    pass 
                elif current_entry_level_rank > prev_level_rank + 1:
                    if prev_entry['level'] == "H1" and entry['level'] == "H3":
                        entry['level'] = "H2"
                        current_entry_level_rank = 2
            
            final_outline.append(entry)
            last_entry_text = entry['text']
            last_entry_page = entry['page']
            last_entry_level_rank = current_entry_level_rank
        
        return final_outline

    def process_pdf(self, input_pdf_path):
       
        print(f"Extracting text elements from {input_pdf_path}...")
        self.extract_text_elements(input_pdf_path)
        
        title_text, title_font_size, title_bbox = self.identify_document_title()
        
        if title_text and title_bbox:
            filtered_pages_data = []
            for page_num, page_elements in enumerate(self.pages_data):
                if page_num + 1 == 1: # Only filter on the first page
                    filtered_elements = []
                    for element in page_elements:
                        element_rect = fitz.Rect(element['bbox'])
                        title_rect = fitz.Rect(title_bbox)
                        if not element_rect.intersects(title_rect) or \
                           (abs(element['font_size'] - title_font_size) > 0.1 and not element_rect.almost_contains(title_rect)):
                            filtered_elements.append(element)
                    filtered_pages_data.append(filtered_elements)
                else:
                    filtered_pages_data.append(page_elements)
            self.pages_data = filtered_pages_data # Update self.pages_data
        
        self._determine_heading_font_map(exclude_font_size=title_font_size)
        
        print("Identifying headings...")
        outline = self.identify_headings()

        return {
            "title": title_text,
            "outline": outline
        }

def main():
    
    input_dir = "input"  # Changed for local testing
    output_dir = "output" # Changed for local testing

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"Scanning for PDFs in {input_dir}...")
    pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith(".pdf")]

    if not pdf_files:
        print(f"No PDF files found in {input_dir}. Please ensure PDFs are in a folder named 'input' in the same directory as solution.py")
        return

    for filename in pdf_files:
        input_pdf_path = os.path.join(input_dir, filename)
        output_json_filename = filename.replace(".pdf", ".json")
        output_json_path = os.path.join(output_dir, output_json_filename)

        print(f"\n--- Processing '{filename}' ---")
        extractor = PDFOutlineExtractor()
        output_data = extractor.process_pdf(input_pdf_path)

        try:
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            print(f"Successfully generated '{output_json_filename}' at '{output_json_path}'")
        except IOError as e:
            print(f"Error writing output JSON for {filename}: {e}")
        except Exception as e:
            print(f"An unexpected error occurred while writing JSON for {filename}: {e}")

if __name__ == "__main__":
    main()
