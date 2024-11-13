let igvBrowser;
let settings;
let activeRowIndex = 0;
let addChrPrefix = false;

// Load settings when the page loads
fetch('/bed_generator/settings')
    .then(response => response.json())
    .then(data => {
        settings = data;
        // Set the default assembly in the dropdown
        document.getElementById('genome-select').value = settings.defaultAssembly === 'GRCh38' ? 'hg38' : 'hg19';
    });

document.addEventListener('DOMContentLoaded', function () {
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
                color: "darkgreen", // Changed color to dark purple
                features: bedContent.split('\n').map(line => {
                    var parts = line.split('\t');
                    return {
                        chr: parts[0],
                        start: parseInt(parts[1]),
                        end: parseInt(parts[2]),
                        name: parts[3] || ''
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
    const results = JSON.parse(document.getElementById('bedContent').value);

    fetch('/bed_generator/adjust_padding', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            padding_5: padding5,
            padding_3: padding3,
            snp_padding_5: snpPadding5,
            snp_padding_3: snpPadding3,
            use_separate_snp_padding: useSeparateSnpPadding,
            results: results
        }),
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            updateTable(data.results);
            document.getElementById('bedContent').value = JSON.stringify(data.results);
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
        const chrPrefix = addChrPrefix ? 'chr' : '';
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

function downloadBED(bedType) {
    const results = JSON.parse(document.getElementById('bedContent').value);
    const filenamePrefix = document.getElementById('bedFileNamePrefix').value;
    const padding5 = parseInt(document.getElementById('paddingInput5').value) || 0;
    const padding3 = parseInt(document.getElementById('paddingInput3').value) || 0;
    const useSeparateSnpPadding = document.getElementById('separateSnpPadding').checked;
    const snpPadding5 = useSeparateSnpPadding ? (parseInt(document.getElementById('snpPadding5').value) || 0) : padding5;
    const snpPadding3 = useSeparateSnpPadding ? (parseInt(document.getElementById('snpPadding3').value) || 0) : padding3;

    fetch(`/bed_generator/download_bed/${bedType}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 
            results: results, 
            filename_prefix: filenamePrefix,
            add_chr_prefix: addChrPrefix,
            padding_5: padding5,
            padding_3: padding3,
            use_separate_snp_padding: useSeparateSnpPadding,
            snp_padding_5: snpPadding5,
            snp_padding_3: snpPadding3
        })
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
    refreshIGV();
    updateTableWithChrPrefix();
}

function updateTableWithChrPrefix() {
    const table = document.querySelector('.table');
    const rows = table.querySelectorAll('tbody tr');
    rows.forEach((row, index) => {
        const chrCell = row.cells[0];
        const chrValue = chrCell.textContent.trim();
        if (addChrPrefix && !chrValue.startsWith('chr')) {
            chrCell.textContent = 'chr' + chrValue;
        } else if (!addChrPrefix && chrValue.startsWith('chr')) {
            chrCell.textContent = chrValue.substring(3);
        }
        updateResult(chrCell, index, 'loc_region');
    });
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
    tableBody.innerHTML = ''; // Clear existing rows

    results.forEach((result, index) => {
        const row = document.createElement('tr');
        row.onclick = function() { setActiveRow(this, index); };
        
        row.innerHTML = `
            <td>${result.loc_region}</td>
            <td>${result.loc_start}</td>
            <td>${result.loc_end}</td>
            <td>${result.entrez_id}</td>
            <td>${result.gene}</td>
            <td>${result.accession}</td>
            <td>${result.exon_id}</td>
            <td>${result.exon_number}</td>
            <td>${result.transcript_biotype}</td>
            <td>${result.mane_transcript}</td>
            <td>${result.mane_transcript_type}</td>
        `;
        
        tableBody.appendChild(row);
    });

    // Update the hidden input with the new results
    document.getElementById('bedContent').value = JSON.stringify(results);
    currentResults = results; // Update the global currentResults variable
}

function updateIGV(results) {
    if (igvBrowser) {
        igvBrowser.removeAllTracks(); // Remove all existing tracks

        const bedFeatures = results.map(result => ({
            chr: result.loc_region,
            start: parseInt(result.loc_start),
            end: parseInt(result.loc_end),
            name: result.gene
        }));

        const bedTrack = {
            name: 'BED Track',
            type: 'annotation',
            format: 'bed',
            features: bedFeatures,
            displayMode: 'EXPANDED',
            color: 'rgb(0, 0, 150)'
        };

        igvBrowser.loadTrack(bedTrack).then(() => {
            console.log('IGV track updated successfully');
            if (results.length > 0) {
                const firstResult = results[0];
                const padding = 100; // Add some padding for better visibility
                igvBrowser.goto(
                    firstResult.loc_region,
                    Math.max(0, parseInt(firstResult.loc_start) - padding),
                    parseInt(firstResult.loc_end) + padding
                );
            }
        }).catch(error => {
            console.error('Error updating IGV track:', error);
        });
    } else {
        console.warn('IGV browser not initialized');
    }
}