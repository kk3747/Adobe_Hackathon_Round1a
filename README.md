PDF Outline Extractor - Adobe Hackathon Round 1A Solution

This project implements the solution for Round 1A of the Adobe Hackathon, focusing on extracting a structured outline (Title, H1, H2, H3 with page numbers) from PDF documents and outputting it in a JSON format. I developed this solution to address the problem statement's requirement for machine understanding of PDF document structures.

My Project Structure:

    adobe_round1a/
    ├── input/
    │   └── *.pdf
    ├── output/
    ├── .dockerignore
    ├── Dockerfile
    ├── main.py
    ├── README.md
    └── requirements.txt

1. Approach
My core approach to this challenge is to programmatically "understand" the visual and textual cues within a PDF that indicate hierarchical structure, much like a human would. Given the constraints of no external models or network calls, I relied entirely on a robust heuristic-based system.


Here's a breakdown of my methodology:

Granular Text Element Extraction: I utilize PyMuPDF (fitz) to extract every text "span" from the PDF. Crucially, this includes rich metadata such as the text content itself, its precise font size, whether it's bold or italic, and its exact bounding box coordinates. This detailed information forms the foundation for all subsequent analysis.

Logical Line Reconstruction: Individual text spans, which can sometimes be fragmented by the PDF rendering process, are intelligently grouped back into coherent logical lines. This is achieved by analyzing their vertical proximity (line_y0 coordinate), ensuring that a complete heading or sentence is treated as a single unit.

Document Title Identification: I identify the main document title by focusing on the first page. I look for the text block with the largest font size, combining any contiguous lines that share this prominent styling. I also incorporate basic filters to prevent common elements like author lists or affiliations from being mistakenly identified as the main title.

Dynamic Heading Font Map Generation: I analyze the distribution of all unique font sizes throughout the document. I then identify a set of the largest, most distinct font sizes, applying a slight tolerance (e.g., 1.0 point difference) to group visually similar sizes. These distinct font "levels" are then heuristically mapped as candidates for H1, H2, and H3. Critically, the font size of the already identified document title is explicitly excluded from this mapping to prevent its misclassification as a heading.

Multi-Factor Heading Classification: For each reconstructed line, I employ a combination of heuristics to classify it as an H1, H2, H3, or regular body text:

Font Properties: I check if the line's font size (or a very close size within tolerance) matches one of the established H1, H2, or H3 font map entries. The presence of bold or italic styling significantly boosts a line's candidacy as a heading.

Structural Patterns: I use regular expressions to detect strong structural patterns:

Bullet Point Prefixes: Bullet characters (•, *, -) are recognized as strong indicators for lower-level headings, typically classified as H3.

Text Followed by Colon: I specifically look for text segments that end with a colon (e.g., "Key Point:"). If concise and not already classified by a stronger rule, these are assigned as H3.

Line Characteristics & Filtering: Headings are generally concise. I apply filters to disqualify lines that are too long (e.g., over 15 words or 120 characters) or end with a period, unless they possess overwhelming heading-like features (e.g., a strong numeric pattern or a bolded prefix).

Positional Filtering: I implement robust filters to eliminate common header and footer elements (page numbers, running titles, author lines, URLs, journal names) based on their content patterns, font size, and consistent vertical position at the top or bottom margins of pages.

Hierarchical Refinement: A final post-processing step aims to ensure the logical flow of the outline, for instance, promoting an H3 to an H2 if it directly follows an H1 without an intermediate H2.

Output Generation: The extracted document title and the classified hierarchical headings are then formatted into the specified JSON structure.


2. Models or Libraries Used

My solution is entirely based on heuristic rules and does not utilize any external machine learning models. This adheres to the offline execution and model size constraints.

The primary and sole external library I use is:

PyMuPDF (fitz): This is a highly efficient and versatile Python binding for MuPDF, which I leverage for robust PDF text and metadata extraction.

Installation: pip install PyMuPDF


3. How to Build and Run My Solution

My solution is designed for execution within a Docker container, ensuring a consistent and isolated environment as required by the hackathon.

Dockerfile is Provided:
The Dockerfile is already provided in the root of the adobe_round1a project directory (alongside main.py).

Prepare Input/Output Directories:
I expect an input/ directory and an output/ directory to be present in your local adobe_round1a project folder.

Input: Please place the PDF files you wish to process inside the input/ directory.

Output: The generated JSON files (e.g., filename.json for filename.pdf) will be saved directly into the output/ directory.


Build the Docker Image:

Navigate to your adobe_round1a project's root directory in the terminal and execute the build command:

docker build -t adobe_round1a .

Run the Docker Container:
After successfully building the image, run the solution using the specified command:

docker run --rm -v "$(pwd)/input:/app/input:ro" -v "$(pwd)/output:/app/output" --network none adobe_round1a


adobe_round1a: This is the name of the Docker image I built.

The main.py script inside the container will automatically process all PDF files found in /app/input and save the corresponding .json outline files into /app/output.