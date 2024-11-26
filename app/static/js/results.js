let igvBrowser;
let settings;
let activeRowIndex = 0;
let addChrPrefix = false;
let currentSortColumn = -1;
let sortDirection = 1; // 1 for ascending, -1 for descending
let utrStates = {
    'none': null,
    'both': null,
    '5only': null,
    '3only': null
};
let currentUTRState = 'none';
let igvTracks = [];  // Store track references
let originalResults = null;
let manePlusSelections = new Map();

// Load settings when the page loads
fetch('/bed_generator/settings')
    .then(response => response.json())
    .then(data => {
        settings = data;
        // Set the default assembly in the dropdown
        document.getElementById('genome-select').value = settings.defaultAssembly === 'GRCh38' ? 'hg38' : 'hg19';
    });

document.addEventListener('DOMContentLoaded', function () {
    // Store initial state WITHOUT filtering
    const initialResults = JSON.parse(document.getElementById('bedContent').value);
    originalResults = initialResults;
    
    // Check for MANE Plus Clinical transcripts
    if (!handleManePlusTranscripts(initialResults)) {
        // Only update table if no MANE Plus Clinical transcripts found
        updateTable(initialResults);
    }
    
    loadIGV();

    // Add event listener to the file input for uploading BED files
    const uploadButton = document.getElementById('bedFileUpload');
    if (uploadButton) {
        uploadButton.addEventListener('change', handleFileUpload);
    }

    // Add event listener for the new checkbox
    const chrPrefixCheckbox = document.getElementById('addChrPrefix');
    if (chrPrefixCheckbox) {
        chrPrefixCheckbox.addEventListener('change', toggleChrPrefix);
    }

    document.getElementById('separateSnpPadding').addEventListener('change', function() {
        const snpPaddingInputs = document.getElementById('snpPaddingInputs');
        snpPaddingInputs.style.display = this.checked ? 'block' : 'none';
    });

    // Initialize all tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    });
});

function loadIGV() {
    var igvDiv = document.getElementById('igv-div');
    
    var loadingIndicator = document.createElement('div');
    loadingIndicator.id = 'igv-loading';
    loadingIndicator.innerHTML = 'Loading IGV...';
    igvDiv.appendChild(loadingIndicator);

    var genome = document.getElementById('genome-select').value;

    var results = JSON.parse(document.getElementById('bedContent').value);
    var bedContent = createBedContent(results);

    // Determine the locus to zoom into (e.g., the first region in the BED content)
    var firstRegion = bedContent.split('\n')[0].split('\t');
    var start = Math.max(0, parseInt(firstRegion[1]) - 350); // Zoomed out by 350bp (200 + 150)
    var end = parseInt(firstRegion[2]) + 350; // Zoomed out by 350bp (200 + 150)
    var locus = `${firstRegion[0]}:${start}-${end}`;

    var options = {
        genome: genome,
        locus: locus,  // Zoom into the first region with 350bp padding
        tracks: [
            {
                name: "Custom BED",
                type: "annotation",
                format: "bed",
                color: "darkgreen",
                features: results.map(result => {
                    return {
                        chr: addChrPrefix && !result.loc_region.startsWith('chr') ? 
                            'chr' + result.loc_region : 
                            result.loc_region,
                        start: parseInt(result.loc_start),
                        end: parseInt(result.loc_end),
                        name: result.gene || '',
                        score: 1000,
                        strand: result.strand === -1 ? '-' : '+'
                    };
                }),
                displayMode: "EXPANDED"
            }
        ]
    };

    igv.createBrowser(igvDiv, options)
        .then(function (browser) {
            console.log('IGV browser created successfully');
            igvBrowser = browser;
            document.getElementById('igv-loading').remove();
            
            // Set the first row as active by default
            const firstRow = document.querySelector('.table tbody tr');
            if (firstRow) {
                setActiveRow(firstRow, 0);
            }
        })
        .catch(function(error) {
            console.error('Error creating IGV browser:', error);
            document.getElementById('igv-loading').innerHTML = 'Error loading IGV. Please try again.';
        });
}

function applyPadding() {
    const padding5 = parseInt(document.getElementById('paddingInput5').value) || 0;
    const padding3 = parseInt(document.getElementById('paddingInput3').value) || 0;
    const useSeparateSnpPadding = document.getElementById('separateSnpPadding').checked;
    const snpPadding5 = useSeparateSnpPadding ? (parseInt(document.getElementById('snpPadding5').value) || 0) : padding5;
    const snpPadding3 = useSeparateSnpPadding ? (parseInt(document.getElementById('snpPadding3').value) || 0) : padding3;
    
    // Get the current state of results (includes UTR changes)
    const bedContentElement = document.getElementById('bedContent');
    const currentResults = JSON.parse(bedContentElement.value);

    fetch('/bed_generator/adjust_padding', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            padding_5: padding5,
            padding_3: padding3,
            use_separate_snp_padding: useSeparateSnpPadding,
            snp_padding_5: snpPadding5,
            snp_padding_3: snpPadding3,
            include_5utr: document.getElementById('include5UTR').checked,
            include_3utr: document.getElementById('include3UTR').checked,
            results: currentResults,  // Use current state instead of original
            is_padding_update: true   // New flag to indicate this is a padding update
        }),
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            updateTable(data.results);
            bedContentElement.value = JSON.stringify(data.results);
            refreshIGV();
        } else {
            console.error('Error applying padding:', data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
    });
}


function addFileUploadButton() {
    const igvDiv = document.getElementById('igv-div');
    const uploadButton = document.createElement('input');
    uploadButton.type = 'file';
    uploadButton.id = 'bedFileUpload';
    uploadButton.accept = '.bed';
    uploadButton.style.display = 'none';

    const uploadLabel = document.createElement('label');
    uploadLabel.htmlFor = 'bedFileUpload';
    uploadLabel.className = 'btn btn-primary mt-2';
    uploadLabel.textContent = 'Upload existing BED File for comparison';

    igvDiv.parentNode.insertBefore(uploadLabel, igvDiv.nextSibling);
    igvDiv.parentNode.insertBefore(uploadButton, uploadLabel);

    uploadButton.addEventListener('change', handleFileUpload);
}

function handleFileUpload(event) {
    const file = event.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const content = e.target.result;
            addBedTrackToIGV(content, file.name);
            compareBedFiles(content);
        };
        reader.readAsText(file);
    }
}

function addBedTrackToIGV(content, fileName) {
    if (igvBrowser) {
        igvBrowser.loadTrack({
            name: fileName,
            type: "annotation",
            format: "bed",
            color: "yellow",
            features: content.split('\n').map(line => {
                const parts = line.split('\t');
                return {
                    chr: parts[0],
                    start: parseInt(parts[1]),
                    end: parseInt(parts[2]),
                    name: parts[3] || ''
                };
            }),
            displayMode: "EXPANDED"
        }).then(function() {
            console.log('New BED track added successfully');
        }).catch(function(error) {
            console.error('Error adding new BED track:', error);
            alert('Error adding new BED track. Please try again.');
        });
    }
}

function changeGenome() {
    var genome = document.getElementById('genome-select').value;
    if (igvBrowser) {
        igvBrowser.loadGenome(genome);
    }
}

function createBedContent(results) {
    return results.map(r => {
        const chrValue = r.loc_region;
        const chrPrefix = addChrPrefix && !chrValue.toLowerCase().startsWith('chr') ? 'chr' : '';
        return `${chrPrefix}${r.loc_region}\t${r.loc_start}\t${r.loc_end}\t${r.gene}`;
    }).join('\n');
}

function updateFilenamePrefixForAll() {
    var prefix = document.getElementById('bedFileNamePrefix').value.trim();
    if (prefix) {
        localStorage.setItem('bedFileNamePrefix', prefix);
    } else {
        localStorage.removeItem('bedFileNamePrefix');
    }
}

function downloadRawBed() {
    const results = JSON.parse(document.getElementById('bedContent').value);
    const filenamePrefix = document.getElementById('bedFileNamePrefix').value;
    const addChrPrefix = document.getElementById('addChrPrefix').checked;
    
    // Create bed content directly from table data
    const bedContent = results.map(r => {
        // Only add chr prefix if it's not already there
        const chrValue = r.loc_region;
        const chrPrefix = addChrPrefix && !chrValue.toLowerCase().startsWith('chr') ? 'chr' : '';
        return `${chrPrefix}${r.loc_region}\t${r.loc_start}\t${r.loc_end}\t${r.gene}`;
    }).join('\n');
    
    // Download file
    const timestamp = new Date().toISOString().slice(0,19).replace(/[-:]/g, '').replace('T', '_');
    const filename = filenamePrefix ? 
        `${filenamePrefix}_${timestamp}_raw.bed` : 
        `${timestamp}_raw.bed`;
        
    const blob = new Blob([bedContent], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

function downloadCustomBed(bedType) {
    const results = JSON.parse(document.getElementById('bedContent').value);
    const filenamePrefix = document.getElementById('bedFileNamePrefix').value;
    const addChrPrefix = document.getElementById('addChrPrefix').checked;
    
    fetch('/bed_generator/download_custom_bed/' + bedType, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            results: results,
            filename_prefix: filenamePrefix,
            add_chr_prefix: addChrPrefix
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.content) {
            // Download file
            const blob = new Blob([data.content], { type: 'text/plain' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = data.filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        }
    })
    .catch(error => console.error('Error:', error));
}

function downloadBedFile(bedType, data) {
    fetch(`/bed_generator/download_bed/${bedType}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            alert('Error: ' + data.error);
        } else {
            const blob = new Blob([data.content], { type: 'text/plain' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = data.filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An unexpected error occurred.');
    });
}

function downloadBEDSet() {
    const results = JSON.parse(document.getElementById('bedContent').value);
    fetch('/bed_generator/download_bed_set', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ results: results }),
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.error) {
            throw new Error(data.error);
        }
        Object.entries(data).forEach(([filename, content]) => {
            const blob = new Blob([content], { type: 'text/plain' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        });
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An error occurred while downloading the BED set: ' + error.message);
    });
}

function showSubmitModal() {
    var submitModal = new bootstrap.Modal(document.getElementById('submitModal'));
    submitModal.show();
}

function getInitialQueryAndPadding() {
    const padding5 = parseInt(document.getElementById('paddingInput5').value) || 0;
    const padding3 = parseInt(document.getElementById('paddingInput3').value) || 0;
    const useSeparateSnpPadding = document.getElementById('separateSnpPadding').checked;
    const snpPadding5 = useSeparateSnpPadding ? (parseInt(document.getElementById('snpPadding5').value) || 0) : padding5;
    const snpPadding3 = useSeparateSnpPadding ? (parseInt(document.getElementById('snpPadding3').value) || 0) : padding3;

    let updatedInitialQuery = { ...initialQuery };
    updatedInitialQuery.padding_5 = padding5;
    updatedInitialQuery.padding_3 = padding3;
    updatedInitialQuery.use_separate_snp_padding = useSeparateSnpPadding;
    updatedInitialQuery.snp_padding_5 = snpPadding5;
    updatedInitialQuery.snp_padding_3 = snpPadding3;

    return {
        initialQuery: updatedInitialQuery,
        padding_5: padding5,
        padding_3: padding3,
        snp_padding_5: snpPadding5,
        snp_padding_3: snpPadding3,
        use_separate_snp_padding: useSeparateSnpPadding
    };
}

function submitForReview() {
    console.log("Starting submitForReview function");
    const results = JSON.parse(document.getElementById('bedContent').value);
    const fileName = document.getElementById('bedFileName').value.trim();
    const indexUrl = document.querySelector('[data-index-url]').getAttribute('data-index-url');
    const assembly = document.getElementById('genome-select').value;

    const { initialQuery, padding_5, padding_3 } = getInitialQueryAndPadding();

    // Add padding information to initialQuery
    initialQuery.padding_5 = padding_5;
    initialQuery.padding_3 = padding_3;

    console.log("Updated Initial Query:", initialQuery);

    if (!fileName && !existingFileId) {
        alert('Please enter a valid name for your BED file or select an existing file to update.');
        return;
    }

    fetch('/bed_generator/submit_for_review', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
            results: results,
            fileName: fileName,
            initialQuery: initialQuery,
            assembly: assembly
        }),
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`HTTP error! status: ${response.status}, body: ${text}`);
            });
        }
        return response.json();
    })
    .then(data => {
        console.log("Response from server:", data);
        if (data.success) {
            alert('BED file submitted for review successfully! Please note that submissions will remain pending and require final sign-off by an authorised clinical scientist. This can be performed in the Management tab.');
            
            const submitModal = bootstrap.Modal.getInstance(document.getElementById('submitModal'));
            submitModal.hide();
            window.location.href = indexUrl;
        } else {
            throw new Error(data.error || 'Unknown error occurred');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An error occurred while submitting the BED file: ' + error.message);
    });
}

function adjustValue(button, adjustment, index, field) {
    const input = button.parentElement.querySelector('input');
    const currentValue = parseInt(input.value, 10);
    const newValue = currentValue + adjustment;
    input.value = newValue;
    updateResult(input, index, field);
    refreshIGV();
}

function refreshIGV() {
    if (igvBrowser) {
        igvBrowser.removeAllTracks();
        igvBrowser = null; // Clear the existing IGV browser instance
        document.getElementById('igv-div').innerHTML = ''; // Clear the IGV div content
        loadIGV(); // Re-initialize the IGV browser
    }
}

function setActiveRow(row, index) {
    // Remove active class from all rows
    document.querySelectorAll('.table tbody tr').forEach(tr => tr.classList.remove('active-row'));
    
    // Add active class to clicked row
    row.classList.add('active-row');
    
    // Update active row index
    activeRowIndex = index;
    
    // Update IGV viewer
    updateIGVLocus();
}

function updateIGVLocus() {
    if (igvBrowser) {
        const results = JSON.parse(document.getElementById('bedContent').value);
        const activeResult = results[activeRowIndex];
        const start = Math.max(0, parseInt(activeResult.loc_start) - 150);
        const end = parseInt(activeResult.loc_end) + 150;
        const locus = `${activeResult.loc_region}:${start}-${end}`;
        igvBrowser.search(locus);
    }
}

function addNewLine() {
    if (!isEditingAllowed) {
        alert('Editing is currently disabled. Please enable editing to add new lines.');
        return;
    }
    
    const results = JSON.parse(document.getElementById('bedContent').value);
    const newLine = {
        loc_region: '',
        loc_start: '',
        loc_end: '',
        entrez_id: '',
        gene: '',
        accession: '',
        exon_id: '',
        exon_number: '',
        transcript_biotype: '',
        mane_transcript: '',
        mane_transcript_type: ''
    };
    results.push(newLine);
    document.getElementById('bedContent').value = JSON.stringify(results);
    
    const tableBody = document.querySelector('.table tbody');
    const newRow = document.createElement('tr');
    newRow.onclick = function() { setActiveRow(this, results.length - 1); };
    newRow.innerHTML = `
        <td contenteditable="true" onblur="updateResult(this, ${results.length - 1}, 'loc_region')"></td>
        <td>
            <div class="input-group">
                <input type="number" class="form-control form-control-sm" value="" onchange="updateResult(this, ${results.length - 1}, 'loc_start')">
            </div>
        </td>
        <td>
            <div class="input-group">
                <input type="number" class="form-control form-control-sm" value="" onchange="updateResult(this, ${results.length - 1}, 'loc_end')">
            </div>
        </td>
        <td contenteditable="true" onblur="updateResult(this, ${results.length - 1}, 'entrez_id')"></td>
        <td contenteditable="true" onblur="updateResult(this, ${results.length - 1}, 'gene')"></td>
        <td contenteditable="true" onblur="updateResult(this, ${results.length - 1}, 'accession')"></td>
        <td contenteditable="true" onblur="updateResult(this, ${results.length - 1}, 'exon_id')"></td>
        <td contenteditable="true" onblur="updateResult(this, ${results.length - 1}, 'exon_number')"></td>
        <td contenteditable="true" onblur="updateResult(this, ${results.length - 1}, 'transcript_biotype')"></td>
        <td contenteditable="true" onblur="updateResult(this, ${results.length - 1}, 'mane_transcript')"></td>
        <td contenteditable="true" onblur="updateResult(this, ${results.length - 1}, 'mane_transcript_type')"></td>
    `;
    tableBody.appendChild(newRow);
    
    // Scroll to the bottom of the table
    tableBody.parentElement.scrollTop = tableBody.parentElement.scrollHeight;
}

function compareBedFiles(uploadedContent) {
    const generatedResults = JSON.parse(document.getElementById('bedContent').value);
    const uploadedResults = uploadedContent.split('\n').map(line => {
        const parts = line.split('\t');
        return {
            chr: normalizeChromosome(parts[0]),
            start: parseInt(parts[1]),
            end: parseInt(parts[2])
        };
    });

    const uniqueInGenerated = [];
    const uniqueInUploaded = [];

    generatedResults.forEach(generated => {
        const normalizedGeneratedChr = normalizeChromosome(generated.loc_region);
        const overlap = uploadedResults.some(uploaded => 
            uploaded.chr === normalizedGeneratedChr &&
            uploaded.start <= generated.loc_end &&
            uploaded.end >= generated.loc_start
        );

        if (!overlap) {
            uniqueInGenerated.push(`${generated.loc_region}:${generated.loc_start}-${generated.loc_end}`);
        }
    });

    uploadedResults.forEach(uploaded => {
        const overlap = generatedResults.some(generated => 
            normalizeChromosome(generated.loc_region) === uploaded.chr &&
            uploaded.start <= generated.loc_end &&
            uploaded.end >= generated.loc_start
        );

        if (!overlap) {
            uniqueInUploaded.push(`${uploaded.chr}:${uploaded.start}-${uploaded.end}`);
        }
    });

    const comparisonResultElement = document.getElementById('comparisonResult');
    if (uniqueInGenerated.length > 0 || uniqueInUploaded.length > 0) {
        // Clear previous content
        comparisonResultElement.innerHTML = '';

        // Create the link element
        const uniqueRegionsLink = document.createElement('a');
        uniqueRegionsLink.href = '#';
        uniqueRegionsLink.style.color = 'red';
        uniqueRegionsLink.textContent = 'Unique regions detected';

        // Attach the click event listener
        uniqueRegionsLink.addEventListener('click', function(event) {
            event.preventDefault(); // Prevent default anchor behavior
            showUniqueRegionsModal();
        });

        // Append the link to the comparisonResultElement
        comparisonResultElement.appendChild(uniqueRegionsLink);

        populateUniqueRegionsPane(uniqueInGenerated, uniqueInUploaded);
    } else {
        comparisonResultElement.textContent = 'All regions overlap.';
        comparisonResultElement.style.color = 'green';
        document.getElementById('uniqueRegionsPane').style.display = 'none';
    }
}

function showUniqueRegionsModal() {
    const uniqueRegionsModal = new bootstrap.Modal(document.getElementById('uniqueRegionsModal'));
    uniqueRegionsModal.show();
}

function populateUniqueRegionsPane(uniqueInGenerated, uniqueInUploaded) {
    const uniqueRegionsList = document.getElementById('uniqueRegionsList');
    
    if (!uniqueRegionsList) {
        console.error('Required elements not found');
        return;
    }

    uniqueRegionsList.innerHTML = '';

    const addRegionToList = (region, source) => {
        const listItem = document.createElement('li');
        listItem.className = 'list-group-item';
        listItem.textContent = `${source}: ${region}`;
        listItem.style.cursor = 'pointer';
        listItem.addEventListener('click', function() {
            showRegionInIGV(region);
            const uniqueRegionsModal = bootstrap.Modal.getInstance(document.getElementById('uniqueRegionsModal'));
            uniqueRegionsModal.hide();
        });
        uniqueRegionsList.appendChild(listItem);
    };

    if (uniqueInGenerated.length > 0) {
        uniqueInGenerated.forEach(region => addRegionToList(region, 'Generated BED'));
    }

    if (uniqueInUploaded.length > 0) {
        uniqueInUploaded.forEach(region => addRegionToList(region, 'Uploaded BED'));
    }
}

function showRegionInIGV(region) {
    if (igvBrowser) {
        const [chr, range] = region.split(':');
        const [start, end] = range.split('-').map(Number);
        const locus = `${chr}:${start}-${end}`;
        igvBrowser.search(locus);
    }
}

function normalizeChromosome(chr) {
    // Remove 'chr' prefix if present and convert to uppercase for consistency
    return chr.replace(/^chr/i, '').toUpperCase();
}

function toggleChrPrefix() {
    addChrPrefix = document.getElementById('addChrPrefix').checked;
    
    // Get the current results and update them
    const results = JSON.parse(document.getElementById('bedContent').value);
    results.forEach(result => {
        const chrValue = result.loc_region;
        if (addChrPrefix && !chrValue.startsWith('chr')) {
            result.loc_region = 'chr' + chrValue;
        } else if (!addChrPrefix && chrValue.startsWith('chr')) {
            result.loc_region = chrValue.substring(3);
        }
    });
    
    // Update the hidden input with modified results
    document.getElementById('bedContent').value = JSON.stringify(results);
    
    // Update just the table
    updateTable(results);
}

function handleBedFileUpload(event) {
    const files = event.target.files;
    let allCoordinates = [];

    const processFile = (file) => {
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = function(e) {
                const contents = e.target.result;
                const lines = contents.split('\n');
                let coordinates = [];
                for (let line of lines) {
                    const parts = line.trim().split('\t');
                    if (parts.length >= 3) {
                        // Check if the file name ends with "_CNV.bed"
                        if (file.name.endsWith('_CNV.bed')) {
                            coordinates.push(`${parts[0]}:${parts[1]}-${parts[2]}`);
                        } else {
                            // For other BED files, include the gene name if available
                            const geneName = parts.length > 3 ? parts[3] : '';
                            coordinates.push(`${parts[0]}:${parts[1]}-${parts[2]}${geneName ? ' ' + geneName : ''}`);
                        }
                    }
                }
                resolve(coordinates);
            };
            reader.readAsText(file);
        });
    };

    Promise.all(Array.from(files).map(processFile))
        .then(results => {
            allCoordinates = results.flat();
            document.getElementById('coordinates').value = allCoordinates.join('\n');
        });
}

// Combine updateTable and refreshTable into a single function
function updateTable(results) {
    const tableBody = document.querySelector('.table tbody');
    tableBody.innerHTML = '';

    const validResults = results.filter(result => 
        parseInt(result.loc_start) <= parseInt(result.loc_end)
    );

    validResults.forEach((result, index) => {
        const row = document.createElement('tr');
        row.onclick = function() { setActiveRow(this, index); };
        
        // Format status display
        let statusDisplay = '';
        if (result.is_snp) {
            statusDisplay = '<span class="badge bg-info text-white"><i class="fas fa-dna"></i> SNP</span>';
        } else if (result.status) {
            // Apply appropriate styling based on status type
            const statusClass = result.status.includes('MANE') ? 'bg-success' : 'bg-info';
            statusDisplay = `<span class="badge ${statusClass} text-white">${result.status}</span>`;
        }
        
        row.innerHTML = `
            <td>${result.loc_region}</td>
            <td>${result.loc_start}</td>
            <td>${result.loc_end}</td>
            <td>${result.entrez_id}</td>
            <td style="background-color: #d4edda;">${result.gene}</td>
            <td>${result.accession}</td>
            <td>${result.exon_id}</td>
            <td>${result.exon_number}</td>
            <td>${result.transcript_biotype}</td>
            <td>${result.mane_transcript}</td>
            <td>${statusDisplay}</td>
        `;
        
        tableBody.appendChild(row);
    });

    document.getElementById('bedContent').value = JSON.stringify(validResults);
    currentResults = validResults;
}

function updateIGV(results) {
    if (!igvBrowser) return;

    // Create bed features from results
    const bedFeatures = results.map(result => ({
        chr: addChrPrefix && !result.loc_region.startsWith('chr') ? 
            'chr' + result.loc_region : 
            result.loc_region,
        start: parseInt(result.loc_start),
        end: parseInt(result.loc_end),
        name: result.gene || 'Unknown',
        score: 1000,
        strand: result.strand === -1 ? '-' : '+'
    }));

    // Find existing custom track
    const existingTrack = igvBrowser.trackViews.find(trackView => 
        trackView.track.name === 'Custom BED'
    )?.track;

    if (existingTrack) {
        // Update existing track
        existingTrack.features = bedFeatures;
        igvBrowser.updateViews();
    } else {
        // Create new track if none exists
        const bedTrack = {
            name: 'Custom BED',
            type: 'annotation',
            format: 'bed',
            features: bedFeatures,
            displayMode: 'EXPANDED',
            color: 'rgb(150, 0, 0)'
        };
        igvBrowser.loadTrack(bedTrack);
    }
}

function toggleUTR() {
    const include5 = document.getElementById('include5UTR').checked;
    const include3 = document.getElementById('include3UTR').checked;
    
    if (!originalResults) {
        console.error('Original results not found');
        return;
    }

    // Get current padding values
    const padding5 = parseInt(document.getElementById('paddingInput5').value) || 0;
    const padding3 = parseInt(document.getElementById('paddingInput3').value) || 0;
    const useSeparateSnpPadding = document.getElementById('separateSnpPadding').checked;
    const snpPadding5 = useSeparateSnpPadding ? (parseInt(document.getElementById('snpPadding5').value) || 0) : padding5;
    const snpPadding3 = useSeparateSnpPadding ? (parseInt(document.getElementById('snpPadding3').value) || 0) : padding3;

    // Process each result
    const adjustedResults = originalResults.map(result => {
        // Skip if it's a genomic coordinate
        if (result.is_genomic_coordinate) {
            return result;
        }

        let newStart = result.full_loc_start || result.loc_start;
        let newEnd = result.full_loc_end || result.loc_end;

        // Apply UTR adjustments
        if (result.strand === 1) {  // Positive strand
            if (!include5 && result.five_prime_utr_end) {
                newStart = Math.max(newStart, result.five_prime_utr_end);
            }
            if (!include3 && result.three_prime_utr_start) {
                newEnd = Math.min(newEnd, result.three_prime_utr_start);
            }
        } else {  // Negative strand
            if (!include5 && result.five_prime_utr_end) {
                newEnd = Math.min(newEnd, result.five_prime_utr_end);
            }
            if (!include3 && result.three_prime_utr_start) {
                newStart = Math.max(newStart, result.three_prime_utr_start);
            }
        }

        // Determine if this is a SNP entry
        const is_snp = result.rsid || result.is_snp;

        // Skip padding for SNPs unless separate SNP padding is enabled
        if (is_snp && !useSeparateSnpPadding) {
            return {
                ...result,
                loc_start: newStart,
                loc_end: newEnd
            };
        }

        // Apply appropriate padding
        if (is_snp && useSeparateSnpPadding) {
            newStart -= snpPadding5;
            newEnd += snpPadding3;
        } else if (!is_snp) {
            newStart -= padding5;
            newEnd += padding3;
        }
        
        return {
            ...result,
            loc_start: newStart,
            loc_end: newEnd
        };
    });

    // Update table and other UI elements
    updateTable(adjustedResults);
    document.getElementById('bedContent').value = JSON.stringify(adjustedResults);
    refreshIGV();
}

function downloadFile(content, filename) {
    // Create a blob with the file content
    const blob = new Blob([content], { type: 'text/plain' });
    
    // Create a temporary URL for the blob
    const url = window.URL.createObjectURL(blob);
    
    // Create a temporary link element
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    
    // Append link to body, click it, and remove it
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    // Clean up by revoking the blob URL
    window.URL.revokeObjectURL(url);
}

function handleManePlusTranscripts(results) {
    console.log("Starting handleManePlusTranscripts with:", results);
    
    // Group results by gene and transcript type
    const geneTranscripts = new Map();
    
    for (const result of results) {
        if (!result.gene || !result.status) continue;
        
        if (!geneTranscripts.has(result.gene)) {
            geneTranscripts.set(result.gene, new Set());
        }
        geneTranscripts.get(result.gene).add(result.status);
    }
    
    console.log("Grouped gene transcripts:", Array.from(geneTranscripts.entries()));
    
    // Find genes that have both MANE Select and MANE Plus Clinical
    const genesWithBothTypes = new Map();
    
    for (const [gene, statuses] of geneTranscripts.entries()) {
        console.log(`Checking ${gene} with statuses:`, Array.from(statuses));
        if (statuses.has('MANE Select') && statuses.has('MANE Plus Clinical')) {
            console.log(`${gene} has both transcript types`);
            // Group all results for this gene
            genesWithBothTypes.set(gene, results.filter(r => r.gene === gene));
        }
    }
    
    console.log("Genes with both types:", Array.from(genesWithBothTypes.entries()));
    
    if (genesWithBothTypes.size > 0) {
        console.log("Showing transcript selection modal");
        showTranscriptSelectionModal(genesWithBothTypes);
        return true;
    }
    
    console.log("No genes with both transcript types found");
    return false;
}

function showTranscriptSelectionModal(geneTranscripts) {
    console.log("Setting up modal with transcripts:", geneTranscripts);
    const optionsContainer = document.getElementById('transcriptOptions');
    optionsContainer.innerHTML = '';

    geneTranscripts.forEach((transcripts, gene) => {
        const maneSelect = transcripts.find(t => t.status === 'MANE Select');
        const manePlus = transcripts.find(t => t.status === 'MANE Plus Clinical');
        
        console.log(`Creating options for ${gene}:`, { maneSelect, manePlus });
        
        const geneDiv = document.createElement('div');
        geneDiv.className = 'mb-3';
        geneDiv.innerHTML = `
            <h6 class="mb-2">${gene}</h6>
            <div class="form-check">
                <input class="form-check-input" type="radio" name="transcript_${gene}" 
                       value="mane_select" id="mane_select_${gene}" checked>
                <label class="form-check-label" for="mane_select_${gene}">
                    MANE Select (${maneSelect?.accession || 'N/A'})
                </label>
            </div>
            <div class="form-check">
                <input class="form-check-input" type="radio" name="transcript_${gene}" 
                       value="mane_plus" id="mane_plus_${gene}">
                <label class="form-check-label" for="mane_plus_${gene}">
                    MANE Plus Clinical (${manePlus?.accession || 'N/A'})
                </label>
            </div>
        `;
        optionsContainer.appendChild(geneDiv);
    });

    const modal = document.getElementById('maneSelectionModal');
    console.log("Modal element:", modal);
    if (!modal) {
        console.error("Modal element not found!");
        return;
    }
    
    const bootstrapModal = new bootstrap.Modal(modal);
    console.log("Showing modal");
    bootstrapModal.show();
}

function applyTranscriptSelection() {
    console.log("Applying transcript selection");
    const results = JSON.parse(document.getElementById('bedContent').value);
    const updatedResults = [];
    
    // Get all genes that had selections
    const selections = new Map();
    document.querySelectorAll('[id^="mane_select_"]').forEach(radio => {
        const gene = radio.id.replace('mane_select_', '');
        const selectedType = document.querySelector(`input[name="transcript_${gene}"]:checked`).value;
        selections.set(gene, selectedType === 'mane_select' ? 'MANE Select' : 'MANE Plus Clinical');
    });
    
    console.log("Selected transcript types:", Array.from(selections.entries()));

    // Filter results based on selections
    results.forEach(result => {
        if (!result.gene || !selections.has(result.gene)) {
            // Keep results for genes that didn't have selections
            updatedResults.push(result);
        } else if (result.status === selections.get(result.gene)) {
            // Keep only the selected transcript type for genes that had selections
            updatedResults.push(result);
        }
        // Drop results for unselected transcript types
    });
    
    console.log("Updated results:", updatedResults);

    // Update both the current results and originalResults
    document.getElementById('bedContent').value = JSON.stringify(updatedResults);
    originalResults = updatedResults;
    
    // Update the table with new results
    updateTable(updatedResults);
    
    // Refresh IGV
    refreshIGV();
    
    // Hide the modal
    const modal = bootstrap.Modal.getInstance(document.getElementById('maneSelectionModal'));
    modal.hide();
}

function showBedFlowDiagram() {
    const modalHtml = `
        <div class="modal fade" id="bedFlowModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header bg-light">
                        <h5 class="modal-title">
                            <i class="fas fa-project-diagram me-2"></i>BED File Generation Flow
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="text-center mb-4">
                            <img src="/static/images/bed_flow_diagram.png" alt="BED File Flow Diagram" class="img-fluid rounded shadow-sm">
                        </div>
                        
                        <div class="card">
                            <div class="card-header bg-light">
                                <h6 class="mb-0">
                                    <i class="fas fa-info-circle me-2"></i>How it works
                                </h6>
                            </div>
                            <div class="card-body">
                                <div class="timeline">
                                    <div class="timeline-item mb-3 d-flex">
                                        <div class="timeline-marker me-3">
                                            <span class="badge rounded-pill bg-primary">1</span>
                                        </div>
                                        <div class="timeline-content">
                                            <p class="mb-0">A base BED file is generated from your user input query</p>
                                        </div>
                                    </div>
                                    
                                    <div class="timeline-item mb-3 d-flex">
                                        <div class="timeline-marker me-3">
                                            <span class="badge rounded-pill bg-primary">2</span>
                                        </div>
                                        <div class="timeline-content">
                                            <p class="mb-0">The Base BED download can be modified, and uses your current screen adjustments</p>
                                        </div>
                                    </div>
                                    
                                    <div class="timeline-item mb-3 d-flex">
                                        <div class="timeline-marker me-3">
                                            <span class="badge rounded-pill bg-primary">3</span>
                                        </div>
                                        <div class="timeline-content">
                                            <p class="mb-0">Custom BED profiles use separate settings configured in Settings. These profiles are not affected by padding adjustments made in this screen.</p>
                                        </div>
                                    </div>
                                    
                                    <div class="timeline-item d-flex">
                                        <div class="timeline-marker me-3">
                                            <span class="badge rounded-pill bg-primary">4</span>
                                        </div>
                                        <div class="timeline-content">
                                            <p class="mb-0">Therefore, when submitting BED files for review, only the Base BED file is required. This is stored and used to generate secondary BED profiles as needed.</p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer bg-light">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    </div>
                </div>
            </div>
        </div>

        <style>
            .timeline-marker {
                min-width: 40px;
                text-align: center;
            }
            
            .timeline-item {
                position: relative;
            }
            
            .timeline-item:not(:last-child):before {
                content: '';
                position: absolute;
                left: 19px;
                top: 30px;
                height: calc(100% + 15px);
                width: 2px;
                background-color: #e9ecef;
            }
            
            .modal-lg {
                max-width: 800px;
            }
            
            .badge.rounded-pill {
                width: 25px;
                height: 25px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
        </style>`;
    
    // Add modal to document if it doesn't exist
    if (!document.getElementById('bedFlowModal')) {
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }
    
    // Show the modal
    const modal = new bootstrap.Modal(document.getElementById('bedFlowModal'));
    modal.show();
}

// Add this function to store the original results when they're first loaded
function storeOriginalResults(results) {
    // Store as a data attribute on the bedContent element
    document.getElementById('bedContent').setAttribute('data-original-results', JSON.stringify(results));
}

function updateResults(results) {
    // Store the original results first
    storeOriginalResults(results);
    
    // Update the table and other UI elements as before
    updateTable(results);
    document.getElementById('bedContent').value = JSON.stringify(results);
    refreshIGV();
}

function checkForManePlusTranscripts(results) {
    const manePlusGenes = new Map();
    console.log("Checking for MANE Plus transcripts:", results);

    // First pass: Group transcripts by gene
    for (const result of results) {
        if (result.gene && result.status) {  // Changed from mane_transcript_type to status
            console.log(`Found transcript for ${result.gene}:`, result.status);
            if (!manePlusGenes.has(result.gene)) {
                manePlusGenes.set(result.gene, []);
            }
            manePlusGenes.get(result.gene).push(result);
        }
    }

    console.log("Grouped transcripts:", Array.from(manePlusGenes.entries()));

    // Second pass: Filter to only keep genes that have both transcript types
    for (const [gene, transcripts] of manePlusGenes.entries()) {
        const hasManePlus = transcripts.some(t => t.status === 'MANE Plus Clinical');  // Changed from mane_transcript_type
        const hasManeSelect = transcripts.some(t => t.status === 'MANE Select');  // Changed from mane_transcript_type
        
        console.log(`${gene} - Has MANE Plus: ${hasManePlus}, Has MANE Select: ${hasManeSelect}`);
        
        if (!hasManePlus || !hasManeSelect) {
            manePlusGenes.delete(gene);
        }
    }

    console.log("Filtered genes with both types:", Array.from(manePlusGenes.entries()));

    if (manePlusGenes.size > 0) {
        showTranscriptSelectionModal(manePlusGenes);
        return true;
    }
    return false;
}