document.addEventListener('DOMContentLoaded', () => {
  // State
  let state = {
    currentJobId: null,
    pincode: '',
    skill: '',
    currentPage: 1,
    pageSize: 15,
    pollIntervalId: null,
    maxPages: 3
  };

  // DOM Elements
  const scrapeForm = document.getElementById('scrape-form');
  const pincodeInput = document.getElementById('pincode');
  const skillInput = document.getElementById('skill');
  const maxPagesInput = document.getElementById('max-pages');
  const pagesVal = document.getElementById('pages-val');
  const startBtn = document.getElementById('start-btn');
  const startBtnText = startBtn.querySelector('.btn-text');

  const jobStatusCard = document.getElementById('job-status-card');
  const jobIdEl = document.getElementById('job-id');
  const jobTargetEl = document.getElementById('job-target');
  const jobStatusEl = document.getElementById('job-status');
  const jobProgressEl = document.getElementById('job-progress');
  const jobPagesScrapedEl = document.getElementById('job-pages-scraped');
  const jobRecordsFoundEl = document.getElementById('job-records-found');
  const jobErrorContainer = document.getElementById('job-error-container');
  const jobErrorMsgEl = document.getElementById('job-error-msg');

  const resultsCountBadge = document.getElementById('results-count-badge');
  const exportBtn = document.getElementById('export-btn');
  const tableSearch = document.getElementById('table-search');
  const listingsTableBody = document.querySelector('#listings-table tbody');

  const paginationControls = document.getElementById('pagination-controls');
  const prevPageBtn = document.getElementById('prev-page-btn');
  const nextPageBtn = document.getElementById('next-page-btn');
  const pageIndicator = document.getElementById('page-indicator');

  const prevPincodeInput = document.getElementById('prev-pincode');
  const prevSkillInput = document.getElementById('prev-skill');
  const loadPrevBtn = document.getElementById('load-prev-btn');

  // Cache of current page data for local filtering
  let loadedListings = [];

  // Update Range Slider Label
  maxPagesInput.addEventListener('input', (e) => {
    pagesVal.textContent = e.target.value;
    state.maxPages = parseInt(e.target.value);
  });

  // Handle Form Submit (Start Scraping)
  scrapeForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const pincode = pincodeInput.value.trim();
    const skill = skillInput.value.trim();
    const max_pages = parseInt(maxPagesInput.value);

    // Reset UI and State
    if (state.pollIntervalId) {
      clearInterval(state.pollIntervalId);
    }
    state.pincode = pincode;
    state.skill = skill;
    state.currentPage = 1;
    loadedListings = [];

    setScrapingActive(true);
    showJobCard(true);
    updateJobCard({
      job_id: 'Initializing...',
      skill: skill,
      pincode: pincode,
      status: 'pending',
      pages_scraped: 0,
      records_found: 0,
      error_message: null
    });

    try {
      const response = await fetch('/api/v1/scrape', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pincode, skill, max_pages })
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to start scraping');
      }

      const job = await response.json();
      state.currentJobId = job.job_id;
      
      updateJobCard(job);
      startPolling(job.job_id);
    } catch (error) {
      setScrapingActive(false);
      updateJobCard({
        job_id: 'Error',
        skill: skill,
        pincode: pincode,
        status: 'failed',
        pages_scraped: 0,
        records_found: 0,
        error_message: error.message
      });
    }
  });

  // Load Previous Listings
  loadPrevBtn.addEventListener('click', () => {
    const pincode = prevPincodeInput.value.trim();
    const skill = prevSkillInput.value.trim();

    if (!pincode || !skill) {
      alert('Please fill out both Pincode and Skill to load existing records.');
      return;
    }
    if (!/^\d{6}$/.test(pincode)) {
      alert('Pincode must be exactly 6 digits.');
      return;
    }

    state.pincode = pincode;
    state.skill = skill;
    state.currentPage = 1;
    
    // Hide job card if we are manually loading old ones
    showJobCard(false);
    fetchListings();
  });

  // Export CSV
  exportBtn.addEventListener('click', () => {
    if (!state.pincode || !state.skill) return;
    const url = `/api/v1/export/csv?pincode=${encodeURIComponent(state.pincode)}&skill=${encodeURIComponent(state.skill)}`;
    window.open(url, '_blank');
  });

  // Pagination clicks
  prevPageBtn.addEventListener('click', () => {
    if (state.currentPage > 1) {
      state.currentPage--;
      fetchListings();
    }
  });

  nextPageBtn.addEventListener('click', () => {
    state.currentPage++;
    fetchListings();
  });

  // Local Filter Search
  tableSearch.addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase().trim();
    if (!query) {
      renderTableRows(loadedListings);
      return;
    }

    const filtered = loadedListings.filter(item => 
      (item.name || '').toLowerCase().includes(query) ||
      (item.phone || '').toLowerCase().includes(query) ||
      (item.category || '').toLowerCase().includes(query) ||
      (item.address || '').toLowerCase().includes(query)
    );
    renderTableRows(filtered);
  });

  // Polling Job Status
  function startPolling(jobId) {
    state.pollIntervalId = setInterval(async () => {
      try {
        const response = await fetch(`/api/v1/jobs/${jobId}`);
        if (!response.ok) throw new Error('Failed to fetch job details');

        const job = await response.json();
        updateJobCard(job);

        // Check if finished
        if (['completed', 'failed', 'partial'].includes(job.status)) {
          clearInterval(state.pollIntervalId);
          state.pollIntervalId = null;
          setScrapingActive(false);
          // Load listings
          fetchListings();
        }
      } catch (error) {
        console.error('Polling error:', error);
      }
    }, 1500);
  }

  // Fetch Listings API
  async function fetchListings() {
    listingsTableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 3rem 0;"><div class="spinner"></div>Loading listings...</td></tr>`;
    
    try {
      const url = `/api/v1/listings?pincode=${encodeURIComponent(state.pincode)}&skill=${encodeURIComponent(state.skill)}&page=${state.currentPage}&page_size=${state.pageSize}`;
      const response = await fetch(url);
      
      if (!response.ok) throw new Error('No listings found or API error.');

      const data = await response.json();
      loadedListings = data.items;
      
      resultsCountBadge.textContent = `${data.total} listings`;
      resultsCountBadge.style.display = 'inline-block';
      exportBtn.disabled = data.total === 0;
      tableSearch.disabled = data.total === 0;
      
      renderTableRows(loadedListings);
      updatePagination(data.total);
    } catch (error) {
      listingsTableBody.innerHTML = `
        <tr class="empty-state-row">
          <td colspan="6">
            <div class="empty-state">
              <svg class="empty-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <p>Error loading listings: ${error.message}</p>
            </div>
          </td>
        </tr>
      `;
      exportBtn.disabled = true;
      tableSearch.disabled = true;
      paginationControls.style.display = 'none';
    }
  }

  // Render Table
  function renderTableRows(items) {
    if (!items || items.length === 0) {
      listingsTableBody.innerHTML = `
        <tr class="empty-state-row">
          <td colspan="6">
            <div class="empty-state">
              <svg class="empty-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
              <p>No results fit the current filter query.</p>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    listingsTableBody.innerHTML = items.map(item => {
      // Phone column display
      let phoneHtml = '';
      if (item.phone) {
        phoneHtml = `
          <div class="phone-cell">
            <span class="phone-badge">${item.phone}</span>
            <button class="copy-phone-btn" data-phone="${item.phone}" title="Copy to clipboard">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            </button>
          </div>
        `;
      } else {
        phoneHtml = `<span class="input-helper">Not available</span>`;
      }

      // Rating column display
      let ratingHtml = '';
      if (item.rating) {
        ratingHtml = `
          <div class="rating-pill">
            <svg class="rating-star-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 .587l3.668 7.431 8.2 1.192-5.934 5.787 1.4 8.168L12 18.896l-7.334 3.857 1.4-8.168L.132 9.21l8.2-1.192L12 .587z"/></svg>
            <span>${item.rating}</span>
          </div>
          ${item.reviews ? `<span class="reviews-count">(${item.reviews})</span>` : ''}
        `;
      } else {
        ratingHtml = `<span class="input-helper">-</span>`;
      }

      // Source URL link
      const sourceHtml = item.source_url ? `
        <a href="${item.source_url}" target="_blank" class="source-link-icon" title="View Source Listing">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
        </a>
      ` : '-';

      return `
        <tr>
          <td style="font-weight: 500;">${escapeHtml(item.name)}</td>
          <td>${phoneHtml}</td>
          <td>${ratingHtml}</td>
          <td style="color: var(--text-secondary); font-size: 0.85rem;">${escapeHtml(item.category || '-')}</td>
          <td style="max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.85rem;" title="${escapeHtml(item.address)}">
            ${escapeHtml(item.address || '-')}
          </td>
          <td style="text-align: center;">${sourceHtml}</td>
        </tr>
      `;
    }).join('');

    // Attach click events to copy buttons
    document.querySelectorAll('.copy-phone-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const phone = btn.getAttribute('data-phone');
        copyToClipboard(phone, btn);
      });
    });
  }

  // Update Pagination Controls
  function updatePagination(totalItems) {
    const totalPages = Math.ceil(totalItems / state.pageSize);
    if (totalPages <= 1) {
      paginationControls.style.display = 'none';
      return;
    }

    paginationControls.style.display = 'flex';
    pageIndicator.textContent = `Page ${state.currentPage} of ${totalPages}`;
    prevPageBtn.disabled = state.currentPage === 1;
    nextPageBtn.disabled = state.currentPage === totalPages;
  }

  // Set form state during scrape
  function setScrapingActive(isActive) {
    if (isActive) {
      startBtn.disabled = true;
      startBtnText.textContent = 'Scraping Active...';
      pincodeInput.disabled = true;
      skillInput.disabled = true;
      maxPagesInput.disabled = true;
    } else {
      startBtn.disabled = false;
      startBtnText.textContent = 'Start Scraping';
      pincodeInput.disabled = false;
      skillInput.disabled = false;
      maxPagesInput.disabled = false;
    }
  }

  // Show/Hide Job Card
  function showJobCard(show) {
    jobStatusCard.style.display = show ? 'flex' : 'none';
  }

  // Update Job status UI
  function updateJobCard(job) {
    jobIdEl.textContent = job.job_id || '-';
    jobTargetEl.textContent = `${job.skill || '-'} (${job.pincode || '-'})`;
    
    // Status Badge classes
    jobStatusEl.className = 'status-badge';
    if (job.status === 'pending') jobStatusEl.classList.add('badge-pending');
    else if (job.status === 'running') jobStatusEl.classList.add('badge-running');
    else if (job.status === 'completed') jobStatusEl.classList.add('badge-completed');
    else if (job.status === 'failed') jobStatusEl.classList.add('badge-failed');
    else if (job.status === 'partial') jobStatusEl.classList.add('badge-partial');
    
    jobStatusEl.textContent = job.status;

    // Progress Bar width estimation
    let progressPercent = 0;
    if (job.status === 'completed') {
      progressPercent = 100;
    } else if (job.status === 'running') {
      // Estimate progress based on page scraped vs total requested
      const totalPages = state.maxPages;
      const scraped = job.pages_scraped || 0;
      progressPercent = Math.min(Math.round(((scraped + 0.5) / totalPages) * 100), 95);
    } else if (['failed', 'partial'].includes(job.status)) {
      progressPercent = 100;
    }

    jobProgressEl.style.width = `${progressPercent}%`;
    jobPagesScrapedEl.textContent = `Pages: ${job.pages_scraped || 0}`;
    jobRecordsFoundEl.textContent = `Found: ${job.records_found || 0}`;

    // Error messages
    if (job.error_message) {
      jobErrorContainer.style.display = 'flex';
      jobErrorMsgEl.textContent = job.error_message;
    } else {
      jobErrorContainer.style.display = 'none';
    }
  }

  // Copy helper
  function copyToClipboard(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
      // Success Feedback
      const originalSvg = btn.innerHTML;
      btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--success)"><polyline points="20 6 9 17 4 12"/></svg>`;
      setTimeout(() => {
        btn.innerHTML = originalSvg;
      }, 1500);
    }).catch(err => {
      console.error('Clipboard copy failed:', err);
    });
  }

  // Escape HTML helper
  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
});
