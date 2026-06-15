const storeId = window.location.pathname.split('/').pop();
let selectedCandidateId = null;
let currentStoreData = null;

document.addEventListener('DOMContentLoaded', function() {
    initDatePickers();
    loadStoreView();
    loadStoreEmailLogs();
});

function initDatePickers() {
    const today = new Date();
    const startOfWeek = new Date(today);
    startOfWeek.setDate(today.getDate() - today.getDay() + 1);
    const endOfWeek = new Date(startOfWeek);
    endOfWeek.setDate(startOfWeek.getDate() + 6);

    document.getElementById('startDate').value = formatDate(startOfWeek);
    document.getElementById('endDate').value = formatDate(endOfWeek);
}

function formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function backToMain() {
    window.location.href = '/';
}

function loadStoreView() {
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;

    fetch(`/api/store-view/${storeId}?start_date=${startDate}&end_date=${endDate}&only_published=true`)
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                showToast(data.error, 'error');
                return;
            }
            currentStoreData = data;
            renderStoreStats(data);
            renderStoreView(data);
        })
        .catch(err => {
            showToast('加载门店数据失败', 'error');
            console.error(err);
        });
}

function renderStoreStats(data) {
    const container = document.getElementById('storeStats');

    let totalSchedules = 0;
    let insufficientSlots = 0;
    let totalStaffHours = 0;
    const uniqueEmployees = new Set();

    data.days.forEach(day => {
        day.slots.forEach(slot => {
            totalSchedules += slot.staff.length;
            if (!slot.meets_minimum) {
                insufficientSlots++;
            }
            slot.staff.forEach(s => uniqueEmployees.add(s.employee_id));
        });
        totalStaffHours += day.total_staff * 8;
    });

    container.innerHTML = `
        <div class="store-stat-item">
            <div class="stat-num">${data.days.length}</div>
            <div class="stat-label">排班天数</div>
        </div>
        <div class="store-stat-item">
            <div class="stat-num">${uniqueEmployees.size}</div>
            <div class="stat-label">在岗员工</div>
        </div>
        <div class="store-stat-item ${insufficientSlots > 0 ? 'warn' : ''}">
            <div class="stat-num">${insufficientSlots}</div>
            <div class="stat-label">缺人时段</div>
        </div>
        <div class="store-stat-item">
            <div class="stat-num">${totalSchedules}</div>
            <div class="stat-label">排班总数</div>
        </div>
    `;
}

function renderStoreView(data) {
    const container = document.getElementById('storeViewContent');

    let html = '';

    if (data.conflicts && data.conflicts.length > 0) {
        html += `
            <div class="conflict-report">
                <h5>⚠️ 需人工处理的排班冲突 (${data.conflicts.length})</h5>
                <ul>
                    ${data.conflicts.map(c => `<li>${c.date} ${c.time} - ${c.message}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    data.days.forEach(day => {
        const dayInsufficient = day.slots.filter(s => !s.meets_minimum).length;
        const totalStaff = day.slots.reduce((sum, s) => sum + s.staff.length, 0);
        const dayHours = day.total_staff * 8;

        html += `
            <div class="store-day-section">
                <div class="store-day-header">
                    <h4>${day.date} ${day.day_name}</h4>
                    <div class="store-day-summary">
                        <span class="summary-item">👥 累计排班: ${totalStaff}人次</span>
                        <span class="summary-item ${dayInsufficient > 0 ? 'bad' : ''}">⚠️ 缺人时段: ${dayInsufficient}</span>
                        <span class="summary-item">⏱️ 总工时: ${dayHours}h</span>
                    </div>
                </div>
                <table class="hour-table">
                    <thead>
                        <tr>
                            <th class="hour-col">时段</th>
                            <th>在岗人员</th>
                            <th style="width: 100px;">人数/需求</th>
                            <th style="width: 80px;">高级数</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        day.slots.forEach(slot => {
            const staffHtml = slot.staff.map(s => `
                <span class="staff-tag ${s.skill_level === '高级' ? 'senior' : 'junior'}"
                      onclick="openReplaceModal(${s.schedule_id}, '${s.name}', '${day.date} ${slot.time}')"
                      title="点击替换该员工">
                    <span class="skill-dot"></span>
                    ${s.name}
                </span>
            `).join('');

            const countBadgeClass = slot.meets_minimum ? 'ok' : 'bad';
            const rowClass = slot.meets_minimum ? '' : 'insufficient';

            html += `
                <tr>
                    <td class="hour-cell">${slot.time}</td>
                    <td class="staff-cell ${rowClass}">
                        <div class="cell-header">
                            <div class="staff-tags">
                                ${staffHtml || '<span style="color: #bfbfbf; font-size: 11px;">无人排班</span>'}
                            </div>
                        </div>
                    </td>
                    <td style="text-align: center; padding: 8px;">
                        <span class="count-badge ${countBadgeClass}">${slot.count}/${data.store.min_staff}</span>
                    </td>
                    <td style="text-align: center; padding: 8px; font-weight: 600; color: #fa8c16;">
                        ${slot.senior_count}
                    </td>
                </tr>
            `;
        });

        html += `
                    </tbody>
                </table>
            </div>
        `;
    });

    if (!data.days || data.days.length === 0) {
        html = '<p class="empty-tip">该日期范围内暂无排班数据</p>';
    }

    container.innerHTML = html;
}

function openReplaceModal(scheduleId, employeeName, timeSlot) {
    selectedCandidateId = null;
    document.getElementById('confirmReplaceBtn').disabled = true;

    document.getElementById('replaceScheduleId').value = scheduleId;
    document.getElementById('originalEmployee').textContent = employeeName;
    document.getElementById('replaceTimeSlot').textContent = timeSlot;

    const schedule = findSchedule(scheduleId);
    if (!schedule) {
        showToast('找不到排班记录', 'error');
        return;
    }

    fetch(`/api/schedules/substitutes?store_id=${storeId}&date=${schedule.date}&start_time=${schedule.start_time}&end_time=${schedule.end_time}&exclude_employee_id=${schedule.employee_id}`)
        .then(r => r.json())
        .then(data => {
            renderCandidates(data.candidates || []);
        })
        .catch(err => {
            document.getElementById('candidateList').innerHTML =
                '<p class="empty-tip" style="padding: 20px; font-size: 12px; color: #ff4d4f;">加载候补员工失败</p>';
        });

    document.getElementById('replaceModal').classList.add('show');
}

function findSchedule(scheduleId) {
    if (!currentStoreData) return null;
    for (const day of currentStoreData.days) {
        for (const slot of day.slots) {
            const found = slot.staff.find(s => s.schedule_id === scheduleId);
            if (found) return found;
        }
    }
    return null;
}

function renderCandidates(candidates) {
    const container = document.getElementById('candidateList');

    if (!candidates || candidates.length === 0) {
        container.innerHTML = '<p class="empty-tip" style="padding: 20px; font-size: 12px;">暂无可用的候补员工</p>';
        return;
    }

    container.innerHTML = candidates.map((c) => `
        <div class="candidate-item" onclick="selectCandidate(${c.employee_id}, this)">
            <div class="candidate-info">
                <div>
                    <div class="candidate-name">
                        ${c.name}
                        <span class="candidate-rank">推荐第${c.rank}名</span>
                    </div>
                    <div class="candidate-detail">
                        <span class="skill-badge ${c.skill_level === '高级' ? 'senior' : 'junior'}">${c.skill_level}</span>
                        <span>本周工时: ${c.weekly_hours}h → ${c.new_weekly_hours}h</span>
                        <span>门店熟悉度: ${c.store_familiarity}次</span>
                        <span>可用: ${c.available_time}</span>
                    </div>
                    <div class="reason-tags">
                        ${(c.reasons || []).map((r, i) => 
                            `<span class="reason-tag ${i < 2 ? 'highlight' : ''}">${r}</span>`
                        ).join('')}
                    </div>
                </div>
            </div>
            <div class="candidate-score">
                ${c.score} 分
            </div>
        </div>
    `).join('');
}

function selectCandidate(employeeId, element) {
    selectedCandidateId = employeeId;
    document.querySelectorAll('.candidate-item').forEach(el => el.classList.remove('selected'));
    element.classList.add('selected');
    document.getElementById('confirmReplaceBtn').disabled = false;
}

function closeReplaceModal() {
    document.getElementById('replaceModal').classList.remove('show');
    selectedCandidateId = null;
}

function confirmReplace() {
    const scheduleId = document.getElementById('replaceScheduleId').value;
    const confirmBtn = document.getElementById('confirmReplaceBtn');

    if (!selectedCandidateId) {
        showToast('请选择候补员工', 'warning');
        return;
    }

    confirmBtn.disabled = true;
    confirmBtn.textContent = '替换中...';

    fetch(`/api/schedules/${scheduleId}/replace`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            new_employee_id: selectedCandidateId,
            operator: '店长',
            check_staff_sufficiency: true
        })
    })
    .then(r => {
        if (r.status === 409) {
            return r.json().then(data => {
                const conflictMsg = data.conflicts && data.conflicts.length > 0 
                    ? data.conflicts.map(c => c.message).join('；') 
                    : '替换失败，存在冲突或会导致人员空档';
                showToast(conflictMsg, 'error');
                throw new Error(conflictMsg);
            });
        }
        return r.json();
    })
    .then(data => {
        if (data && data.success) {
            showToast('替换成功，数据已同步', 'success');
            closeReplaceModal();
            Promise.all([
                loadStoreView(),
                new Promise(resolve => setTimeout(resolve, 300))
            ]).then(() => {
                showToast('门店视图、本周汇总已自动更新', 'info');
            });
        } else if (data && data.error) {
            showToast(data.error, 'error');
        } else {
            showToast('替换失败', 'error');
        }
    })
    .catch(err => {
        if (err.message !== '替换失败，存在冲突或会导致人员空档') {
            showToast('替换失败，请重试', 'error');
        }
    })
    .finally(() => {
        confirmBtn.disabled = false;
        confirmBtn.textContent = '确认替换';
    });
}

function exportStoreExcel() {
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;

    window.location.href = `/api/export/excel?start_date=${startDate}&end_date=${endDate}&store_id=${storeId}&mode=store`;
    showToast('正在导出本店排班表...', 'info');
}

function sendStoreEmail() {
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;

    fetch('/api/send-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            start_date: startDate,
            end_date: endDate,
            store_id: parseInt(storeId)
        })
    })
    .then(r => r.json())
    .then(data => {
        showEmailStatus(data);
        setTimeout(() => {
            loadStoreEmailLogs();
        }, 500);
    })
    .catch(err => {
        showToast('发送邮件失败', 'error');
    });
}

function showEmailStatus(data) {
    let html = '<div class="email-status-list">';

    (data.results || []).forEach(r => {
        const statusText = {
            'success': '发送成功',
            'simulated': '模拟发送',
            'no_email': '无邮箱地址',
            'error': '发送失败'
        }[r.status] || r.status;

        html += `
            <div class="email-status-item">
                <span>${r.store_name} → ${r.email || '无邮箱'}</span>
                <span class="status-tag ${r.status}">${statusText}</span>
            </div>
        `;
    });

    html += '</div>';

    showToast(`${data.success_count || 0}/${data.total || 0} 封邮件处理完成`,
        (data.success_count || 0) > 0 ? 'success' : 'warning');

    setTimeout(() => {
        alert('邮件发送状态:\n\n' + (data.results || []).map(r => {
            const statusText = {'success': '✓ 发送成功', 'simulated': '○ 模拟发送', 'no_email': '△ 无邮箱', 'error': '✗ 发送失败'}[r.status] || r.status;
            return `${r.store_name}: ${statusText}${r.message ? ' - ' + r.message : ''}`;
        }).join('\n'));
    }, 300);
}

function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;

    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

function loadStoreEmailLogs() {
    fetch(`/api/email-logs?store_id=${storeId}&limit=10`)
        .then(r => r.json())
        .then(data => {
            renderStoreEmailLogs(data);
        })
        .catch(err => {
            document.getElementById('storeEmailLogs').innerHTML = 
                '<p class="empty-tip" style="padding: 10px; font-size: 11px; color: #ff4d4f;">加载失败</p>';
        });
}

function renderStoreEmailLogs(logs) {
    const container = document.getElementById('storeEmailLogs');

    if (!logs || logs.length === 0) {
        container.innerHTML = '<p class="empty-tip" style="padding: 10px; font-size: 11px;">暂无发送记录</p>';
        return;
    }

    let html = '<div class="store-email-log-list">';
    logs.forEach(log => {
        const statusBadge = `<span class="status-tag ${log.status}">${log.status_text}</span>`;
        const noteHtml = log.error_message ? 
            `<div class="store-email-log-error" title="${log.error_message}">失败: ${log.error_message}</div>` : '';
        const weekHtml = log.week_range ? 
            `<div class="store-email-log-week">周次: ${log.week_range}</div>` : '';
        const senderHtml = log.sender ? 
            `<div class="store-email-log-sender">发送人: ${log.sender}</div>` : '';
        const versionHtml = log.only_published ? 
            '<span style="color:#52c41a;font-size:10px;">[已发布版]</span>' : 
            '<span style="color:#faad14;font-size:10px;">[含草稿]</span>';
        
        html += `
            <div class="store-email-log-item">
                <div class="store-email-log-header">
                    ${statusBadge}
                    <span class="store-email-log-time">${log.sent_at || ''}</span>
                </div>
                <div class="store-email-log-recipient" title="${log.recipient || ''}">
                    ${log.recipient || '-'} ${versionHtml}
                </div>
                ${weekHtml}
                ${senderHtml}
                ${noteHtml}
            </div>
        `;
    });
    html += '</div>';

    container.innerHTML = html;
}

function refreshStoreEmailLogs() {
    loadStoreEmailLogs();
}
