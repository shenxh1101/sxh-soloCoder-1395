let calendar;
let stores = [];
let employees = [];
let currentSchedules = [];
let pendingDeleteScheduleId = null;

document.addEventListener('DOMContentLoaded', function() {
    initDatePickers();
    loadStores();
    loadEmployees();
    initCalendar();
    loadSchedules();
});

function initDatePickers() {
    const today = new Date();
    const nextWeek = new Date(today.getTime() + 7 * 24 * 60 * 60 * 1000);

    document.getElementById('startDate').value = formatDate(today);
    document.getElementById('endDate').value = formatDate(nextWeek);

    document.getElementById('genStartDate').value = formatDate(today);
    document.getElementById('genEndDate').value = formatDate(nextWeek);

    document.getElementById('expStartDate').value = formatDate(today);
    document.getElementById('expEndDate').value = formatDate(nextWeek);
}

function formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function loadStores() {
    fetch('/api/stores')
        .then(r => r.json())
        .then(data => {
            stores = data;
            const storeFilter = document.getElementById('storeFilter');
            const editStore = document.getElementById('editStore');
            const expStoreId = document.getElementById('expStoreId');
            const storeLinks = document.getElementById('storeLinks');

            storeLinks.innerHTML = '';

            data.forEach(store => {
                const option1 = document.createElement('option');
                option1.value = store.id;
                option1.textContent = store.name;
                storeFilter.appendChild(option1);

                const option2 = document.createElement('option');
                option2.value = store.id;
                option2.textContent = store.name;
                editStore.appendChild(option2);

                const option3 = document.createElement('option');
                option3.value = store.id;
                option3.textContent = store.name;
                expStoreId.appendChild(option3);

                const link = document.createElement('button');
                link.className = 'btn btn-block btn-secondary';
                link.style.fontSize = '12px';
                link.style.padding = '6px 10px';
                link.textContent = `→ ${store.name}`;
                link.onclick = () => window.location.href = `/store/${store.id}`;
                storeLinks.appendChild(link);
            });
        });
}

function loadEmployees() {
    fetch('/api/employees')
        .then(r => r.json())
        .then(data => {
            employees = data;
            renderEmployeeList();
            renderEmployeeSelect();
        });
}

function renderEmployeeList() {
    const list = document.getElementById('employeeList');
    list.innerHTML = '';

    employees.forEach(emp => {
        const item = document.createElement('div');
        item.className = 'employee-item';
        item.innerHTML = `
            <span>${emp.name}</span>
            <span class="skill-tag ${emp.skill_level === '高级' ? 'senior' : 'junior'}">${emp.skill_level}</span>
        `;
        list.appendChild(item);
    });
}

function renderEmployeeSelect() {
    const select = document.getElementById('editEmployee');
    select.innerHTML = '';

    employees.forEach(emp => {
        const option = document.createElement('option');
        option.value = emp.id;
        option.textContent = `${emp.name} (${emp.skill_level})`;
        select.appendChild(option);
    });
}

function initCalendar() {
    const calendarEl = document.getElementById('calendar');

    calendar = new FullCalendar.Calendar(calendarEl, {
        locale: 'zh-cn',
        initialView: 'timeGridWeek',
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,timeGridDay'
        },
        slotMinTime: '07:00:00',
        slotMaxTime: '23:00:00',
        allDaySlot: false,
        editable: true,
        eventResizableFromStart: true,
        eventDurationEditable: true,
        eventStartEditable: true,
        dayMaxEvents: true,
        events: [],
        eventClick: function(info) {
            openEditModal(info.event);
        },
        eventDrop: function(info) {
            handleEventDrop(info);
        },
        eventResize: function(info) {
            handleEventResize(info);
        },
        eventDidMount: function(info) {
            const event = info.event;
            const schedule = currentSchedules.find(s => s.id == event.id);
            if (schedule) {
                if (schedule.employee_skill === '高级') {
                    event.setProp('classNames', ['senior-event']);
                } else {
                    event.setProp('classNames', ['junior-event']);
                }
            }
        }
    });

    calendar.render();
}

function loadSchedules() {
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    const storeId = document.getElementById('storeFilter').value;

    let url = `/api/schedules?start_date=${startDate}&end_date=${endDate}`;
    if (storeId) {
        url += `&store_id=${storeId}`;
    }

    fetch(url)
        .then(r => r.json())
        .then(data => {
            currentSchedules = data;
            renderCalendarEvents(data);

            const activeTab = document.querySelector('.tab-btn.active');
            if (activeTab && activeTab.id === 'tab-summary') {
                showSummary();
            } else if (activeTab && activeTab.id === 'tab-workhours') {
                showWorkhours();
            }
        });
}

function refreshAll() {
    loadSchedules();
}

function renderCalendarEvents(schedules) {
    const events = schedules.map(s => ({
        id: s.id,
        title: `${s.employee_name} - ${s.store_name}`,
        start: `${s.date}T${s.start_time}`,
        end: `${s.date}T${s.end_time}`,
        extendedProps: {
            employee_id: s.employee_id,
            store_id: s.store_id,
            employee_skill: s.employee_skill
        }
    }));

    calendar.removeAllEvents();
    events.forEach(e => {
        calendar.addEvent(e);
    });
}

function openGenerateModal() {
    document.getElementById('genResult').style.display = 'none';
    document.getElementById('genBtn').disabled = false;
    document.getElementById('generateModal').classList.add('show');
}

function closeGenerateModal() {
    document.getElementById('generateModal').classList.remove('show');
}

function generateSchedule() {
    const startDate = document.getElementById('genStartDate').value;
    const endDate = document.getElementById('genEndDate').value;

    if (!startDate || !endDate) {
        showToast('请选择日期范围', 'warning');
        return;
    }

    document.getElementById('genBtn').disabled = true;

    fetch('/api/schedules/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            start_date: startDate,
            end_date: endDate
        })
    })
    .then(r => r.json())
    .then(data => {
        const resultDiv = document.getElementById('genResult');
        if (data.success) {
            let html = `
                <div style="background:#f6ffed; border:1px solid #b7eb8f; border-radius:6px; padding:12px;">
                    <p style="color:#52c41a; font-weight:600; margin-bottom:8px;">✓ ${data.message}</p>
            `;

            if (data.summary) {
                html += `<p style="font-size:12px; color:#595959;">${data.summary}</p>`;
            }

            if (data.emp_stats && data.emp_stats.length > 0) {
                html += `
                    <p style="font-size:12px; color:#8c8c8c; margin-top:8px;">员工工时均衡情况：</p>
                    <div style="max-height:120px; overflow-y:auto; font-size:11px; margin-top:4px;">
                `;
                data.emp_stats.forEach(s => {
                    html += `<div style="padding:2px 0;">${s.employee_name}: ${s.total_hours}h (${s.shift_count}个班次)</div>`;
                });
                html += `</div>`;
            }

            if (data.conflicts && data.conflicts.length > 0) {
                html += `
                    <div style="margin-top:10px; background:#fff2f0; border:1px solid #ffccc7; border-radius:4px; padding:8px;">
                        <p style="color:#ff4d4f; font-weight:600; font-size:12px;">⚠️ 以下时段无法自动排班，需人工处理 (${data.conflicts.length})：</p>
                        <ul style="margin-top:4px; padding-left:16px;">
                `;
                data.conflicts.slice(0, 10).forEach(c => {
                    html += `<li style="color:#cf1322; font-size:11px; padding:1px 0;">${c.date} ${c.time} - ${c.message}</li>`;
                });
                if (data.conflicts.length > 10) {
                    html += `<li style="color:#cf1322; font-size:11px;">...还有 ${data.conflicts.length - 10} 条</li>`;
                }
                html += `</ul></div>`;
            }

            html += `</div>`;
            resultDiv.innerHTML = html;
            resultDiv.style.display = 'block';

            showToast(data.message, 'success');
            refreshAll();
        } else {
            resultDiv.innerHTML = `<p style="color:#ff4d4f;">${data.error || '生成失败'}</p>`;
            resultDiv.style.display = 'block';
            showToast(data.error || '生成失败', 'error');
        }
    })
    .catch(err => {
        document.getElementById('genResult').innerHTML = '<p style="color:#ff4d4f;">生成排班失败</p>';
        document.getElementById('genResult').style.display = 'block';
        showToast('生成排班失败', 'error');
    })
    .finally(() => {
        document.getElementById('genBtn').disabled = false;
    });
}

function openExportModal() {
    document.getElementById('expStartDate').value = document.getElementById('startDate').value;
    document.getElementById('expEndDate').value = document.getElementById('endDate').value;
    document.getElementById('exportModal').classList.add('show');
}

function closeExportModal() {
    document.getElementById('exportModal').classList.remove('show');
}

function doExportExcel() {
    const startDate = document.getElementById('expStartDate').value;
    const endDate = document.getElementById('expEndDate').value;
    const storeId = document.getElementById('expStoreId').value;
    const mode = document.getElementById('expMode').value;

    if (!startDate || !endDate) {
        showToast('请选择日期范围', 'warning');
        return;
    }

    let url = `/api/export/excel?start_date=${startDate}&end_date=${endDate}&mode=${mode}`;
    if (storeId) {
        url += `&store_id=${storeId}`;
    }

    window.location.href = url;
    closeExportModal();
    showToast('正在导出Excel...', 'info');
}

function exportExcel() {
    openExportModal();
}

function openEditModal(event) {
    document.getElementById('editScheduleId').value = event.id;
    document.getElementById('editEmployee').value = event.extendedProps.employee_id;
    document.getElementById('editStore').value = event.extendedProps.store_id;
    document.getElementById('editDate').value = event.startStr.split('T')[0];
    document.getElementById('editStartTime').value = event.startStr.split('T')[1].substring(0, 5);
    document.getElementById('editEndTime').value = event.endStr.split('T')[1].substring(0, 5);

    document.getElementById('conflictWarning').style.display = 'none';
    document.getElementById('deleteBtn').style.display = 'inline-block';

    document.getElementById('editModal').classList.add('show');

    checkConflict();
}

function closeEditModal() {
    document.getElementById('editModal').classList.remove('show');
}

function saveSchedule() {
    const scheduleId = document.getElementById('editScheduleId').value;
    const employeeId = document.getElementById('editEmployee').value;
    const storeId = document.getElementById('editStore').value;
    const date = document.getElementById('editDate').value;
    const startTime = document.getElementById('editStartTime').value;
    const endTime = document.getElementById('editEndTime').value;

    fetch(`/api/schedules/${scheduleId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            employee_id: parseInt(employeeId),
            store_id: parseInt(storeId),
            date: date,
            start_time: startTime,
            end_time: endTime
        })
    })
    .then(r => {
        if (r.status === 409) {
            return r.json().then(data => {
                showConflictWarning(data.conflicts);
                showToast('存在冲突，请检查', 'warning');
                throw new Error('conflict');
            });
        }
        return r.json();
    })
    .then(data => {
        if (data.success) {
            showToast('保存成功', 'success');
            closeEditModal();
            refreshAll();
        } else {
            showToast(data.error || '保存失败', 'error');
        }
    })
    .catch(err => {
        if (err.message !== 'conflict') {
            showToast('保存失败', 'error');
        }
    });
}

function deleteSchedule() {
    const scheduleId = document.getElementById('editScheduleId').value;
    pendingDeleteScheduleId = scheduleId;

    fetch(`/api/schedules/${scheduleId}/check-delete`)
        .then(r => r.json())
        .then(data => {
            showDeleteConfirm(data);
        })
        .catch(err => {
            showDeleteConfirm({ has_conflict: false, conflicts: [] });
        });
}

function showDeleteConfirm(impact) {
    const schedule = currentSchedules.find(s => s.id == pendingDeleteScheduleId);
    let text = '确定要删除这条排班吗？';
    if (schedule) {
        text = `确定要删除 ${schedule.employee_name} 在 ${schedule.store_name} ${schedule.date} ${schedule.start_time}-${schedule.end_time} 的排班吗？`;
    }

    document.getElementById('deleteConfirmText').textContent = text;

    const warningDiv = document.getElementById('deleteWarning');
    const forceOption = document.getElementById('forceDeleteOption');
    const forceCheck = document.getElementById('forceDeleteCheck');
    const confirmBtn = document.getElementById('confirmDeleteBtn');

    forceCheck.checked = false;

    if (impact.has_conflict && impact.conflicts && impact.conflicts.length > 0) {
        warningDiv.style.display = 'block';
        warningDiv.innerHTML = `
            <div class="delete-confirm-warning">
                <h5>⚠️ 删除将导致以下问题：</h5>
                <ul>
                    ${impact.conflicts.map(c => `<li>${c.message}</li>`).join('')}
                </ul>
            </div>
        `;
        forceOption.style.display = 'block';
        confirmBtn.disabled = true;

        forceCheck.onchange = function() {
            confirmBtn.disabled = !this.checked;
        };
    } else {
        warningDiv.style.display = 'none';
        forceOption.style.display = 'none';
        confirmBtn.disabled = false;
    }

    closeEditModal();
    document.getElementById('deleteConfirmModal').classList.add('show');
}

function closeDeleteConfirmModal() {
    document.getElementById('deleteConfirmModal').classList.remove('show');
    pendingDeleteScheduleId = null;
}

function confirmDelete() {
    if (!pendingDeleteScheduleId) return;

    const force = document.getElementById('forceDeleteCheck').checked;
    let url = `/api/schedules/${pendingDeleteScheduleId}`;
    if (force) {
        url += '?force=true';
    }

    fetch(url, { method: 'DELETE' })
        .then(r => {
            if (r.status === 409) {
                return r.json().then(data => {
                    showToast(data.conflicts ? data.conflicts[0].message : '删除失败，会导致门店缺人', 'error');
                    throw new Error('conflict');
                });
            }
            return r.json();
        })
        .then(data => {
            if (data.success) {
                showToast('删除成功', 'success');
                closeDeleteConfirmModal();
                refreshAll();
            } else {
                showToast(data.error || '删除失败', 'error');
            }
        })
        .catch(err => {
            if (err.message !== 'conflict') {
                showToast('删除失败', 'error');
            }
        });
}

function handleEventDrop(info) {
    const event = info.event;
    const scheduleId = event.id;
    const date = event.startStr.split('T')[0];
    const startTime = event.startStr.split('T')[1].substring(0, 5);
    const endTime = event.endStr.split('T')[1].substring(0, 5);
    const storeId = event.extendedProps.store_id;
    const employeeId = event.extendedProps.employee_id;

    checkConflictAjax(employeeId, storeId, date, startTime, endTime, scheduleId, function(result) {
        if (result.has_conflict) {
            info.revert();
            showToast(result.conflicts && result.conflicts[0] ? '拖拽失败：' + result.conflicts[0].message : '拖拽失败：存在冲突', 'error');
        } else {
            updateSchedule(scheduleId, {
                date: date,
                start_time: startTime,
                end_time: endTime
            });
        }
    });
}

function handleEventResize(info) {
    const event = info.event;
    const scheduleId = event.id;
    const date = event.startStr.split('T')[0];
    const startTime = event.startStr.split('T')[1].substring(0, 5);
    const endTime = event.endStr.split('T')[1].substring(0, 5);
    const storeId = event.extendedProps.store_id;
    const employeeId = event.extendedProps.employee_id;

    checkConflictAjax(employeeId, storeId, date, startTime, endTime, scheduleId, function(result) {
        if (result.has_conflict) {
            info.revert();
            showToast(result.conflicts && result.conflicts[0] ? '调整失败：' + result.conflicts[0].message : '调整失败：存在冲突', 'error');
        } else {
            updateSchedule(scheduleId, {
                start_time: startTime,
                end_time: endTime
            });
        }
    });
}

function updateSchedule(scheduleId, data) {
    fetch(`/api/schedules/${scheduleId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(r => {
        if (r.status === 409) {
            showToast('保存失败：存在冲突', 'error');
            refreshAll();
            return;
        }
        return r.json();
    })
    .then(data => {
        if (data && data.success) {
            showToast('已更新', 'success');
            refreshAll();
        }
    })
    .catch(() => {});
}

function checkConflict() {
    const employeeId = document.getElementById('editEmployee').value;
    const storeId = document.getElementById('editStore').value;
    const date = document.getElementById('editDate').value;
    const startTime = document.getElementById('editStartTime').value;
    const endTime = document.getElementById('editEndTime').value;
    const scheduleId = document.getElementById('editScheduleId').value;

    if (startTime && endTime && startTime >= endTime) {
        showConflictWarning([{ message: '结束时间必须晚于开始时间' }]);
        return;
    }

    checkConflictAjax(employeeId, storeId, date, startTime, endTime, scheduleId, function(result) {
        if (result.conflicts && result.conflicts.length > 0) {
            showConflictWarning(result.conflicts);
        } else {
            document.getElementById('conflictWarning').style.display = 'none';
        }
    });
}

function checkConflictAjax(employeeId, storeId, date, startTime, endTime, excludeId, callback) {
    if (!employeeId || !storeId || !date || !startTime || !endTime) {
        callback({ has_conflict: false, conflicts: [] });
        return;
    }

    fetch('/api/schedules/check-conflict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            employee_id: parseInt(employeeId),
            store_id: parseInt(storeId),
            date: date,
            start_time: startTime,
            end_time: endTime,
            exclude_schedule_id: excludeId ? parseInt(excludeId) : null,
            check_staff: true
        })
    })
    .then(r => r.json())
    .then(data => {
        callback(data);
    })
    .catch(() => callback({ has_conflict: false, conflicts: [] }));
}

function showConflictWarning(conflicts) {
    const warningDiv = document.getElementById('conflictWarning');
    const list = document.getElementById('conflictList');
    list.innerHTML = '';

    conflicts.forEach(c => {
        const li = document.createElement('li');
        li.textContent = c.message;
        list.appendChild(li);
    });

    warningDiv.style.display = 'block';
}

document.getElementById('editEmployee').addEventListener('change', checkConflict);
document.getElementById('editStore').addEventListener('change', checkConflict);
document.getElementById('editDate').addEventListener('change', checkConflict);
document.getElementById('editStartTime').addEventListener('change', checkConflict);
document.getElementById('editEndTime').addEventListener('change', checkConflict);

function switchTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

    document.getElementById(`tab-${tabName}`).classList.add('active');
    document.getElementById(`content-${tabName}`).classList.add('active');

    if (tabName === 'summary') {
        showSummary();
    } else if (tabName === 'workhours') {
        showWorkhours();
    }
}

function showSummary() {
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;

    if (!startDate || !endDate) {
        showToast('请选择日期范围', 'warning');
        return;
    }

    fetch(`/api/summary?start_date=${startDate}&end_date=${endDate}`)
        .then(r => r.json())
        .then(data => {
            renderSummary(data);
        });
}

function renderSummary(data) {
    const container = document.getElementById('summaryContainer');

    if (!data || data.length === 0) {
        container.innerHTML = '<p class="empty-tip">暂无数据</p>';
        return;
    }

    let html = '';

    data.forEach(day => {
        html += `
            <div class="summary-day">
                <div class="summary-day-header">
                    <h4>${day.date} ${day.day_name}</h4>
                </div>
                <div class="summary-stores">
        `;

        day.stores.forEach(store => {
            html += `
                <div class="summary-store">
                    <h5>${store.store_name}（最低${store.min_staff}人，共${store.total_employees}人，高级${store.senior_count}人）</h5>
                    <table class="time-slot-table">
                        <thead>
                            <tr>
                                <th>时段</th>
                                <th>在岗人员</th>
                                <th>人数</th>
                                <th>高级数</th>
                                <th>状态</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

            store.time_slots.forEach(slot => {
                const staffHtml = slot.staff.map(s =>
                    `<span class="staff-name ${s.skill_level === '高级' ? 'senior' : 'junior'}">${s.name}</span>`
                ).join(' ');

                const statusClass = slot.meets_minimum ? '' : 'insufficient';
                const statusText = slot.meets_minimum ? '正常' : '不足';

                html += `
                    <tr class="${statusClass}">
                        <td>${slot.time}</td>
                        <td>${staffHtml || '-'}</td>
                        <td>${slot.count}</td>
                        <td>${slot.senior_count}</td>
                        <td>${statusText}</td>
                    </tr>
                `;
            });

            html += `
                        </tbody>
                    </table>
                </div>
            `;
        });

        html += `
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

function showWorkhours() {
    const now = new Date();
    const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

    fetch(`/api/workhours?month=${month}`)
        .then(r => r.json())
        .then(data => {
            renderWorkhours(data);
        });
}

function renderWorkhours(data) {
    const container = document.getElementById('workhoursContainer');

    if (!data || !data.employees || data.employees.length === 0) {
        container.innerHTML = '<p class="empty-tip">暂无数据</p>';
        return;
    }

    const totalEmployees = data.employees.length;
    const overtimeCount = data.employees.filter(e => e.is_overtime).length;
    const avgHours = totalEmployees > 0
        ? (data.employees.reduce((sum, e) => sum + e.total_hours, 0) / totalEmployees).toFixed(1)
        : 0;
    const totalHours = data.employees.reduce((sum, e) => sum + e.total_hours, 0).toFixed(1);

    let html = `
        <div class="workhours-stats">
            <div class="stat-card">
                <div class="stat-number">${totalEmployees}</div>
                <div class="stat-label">员工总数</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">${overtimeCount}</div>
                <div class="stat-label">超时员工</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">${avgHours}</div>
                <div class="stat-label">平均工时(小时)</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">${totalHours}</div>
                <div class="stat-label">总工时(小时)</div>
            </div>
        </div>

        <h3 style="margin-bottom: 12px;">${data.month} 工时明细</h3>
        <table class="workhours-table">
            <thead>
                <tr>
                    <th>员工姓名</th>
                    <th>技能等级</th>
                    <th>排班天数</th>
                    <th>总工时(小时)</th>
                    <th>标准工时</th>
                    <th>进度</th>
                    <th>状态</th>
                    <th>超时(小时)</th>
                </tr>
            </thead>
            <tbody>
    `;

    data.employees.forEach(emp => {
        const progress = Math.min(100, (emp.total_hours / data.standard_hours) * 100);
        const progressClass = emp.is_overtime ? 'overtime' : '';
        const rowClass = emp.is_overtime ? 'overtime' : '';
        const statusTag = emp.is_overtime
            ? '<span class="overtime-tag">超时</span>'
            : '<span class="normal-tag">正常</span>';

        html += `
            <tr class="${rowClass}">
                <td>${emp.employee_name}</td>
                <td>${emp.skill_level}</td>
                <td>${emp.schedule_days}</td>
                <td>${emp.total_hours}</td>
                <td>${data.standard_hours}</td>
                <td style="width: 150px;">
                    <div class="progress-bar">
                        <div class="progress-fill ${progressClass}" style="width: ${progress}%"></div>
                    </div>
                </td>
                <td>${statusTag}</td>
                <td>${emp.overtime_hours}</td>
            </tr>
        `;
    });

    html += `
            </tbody>
        </table>
    `;

    container.innerHTML = html;
}

function sendEmail() {
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    const storeId = document.getElementById('storeFilter').value;

    if (!startDate || !endDate) {
        showToast('请选择日期范围', 'warning');
        return;
    }

    fetch('/api/send-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            start_date: startDate,
            end_date: endDate,
            store_id: storeId ? parseInt(storeId) : null
        })
    })
    .then(r => r.json())
    .then(data => {
        showEmailStatus(data);
    })
    .catch(err => {
        showToast('发送邮件失败', 'error');
    });
}

function showEmailStatus(data) {
    let msg = `${data.success_count || 0}/${data.total || 0} 封邮件处理完成`;
    let type = (data.success_count || 0) > 0 ? 'success' : 'warning';
    showToast(msg, type);

    setTimeout(() => {
        const detail = (data.results || []).map(r => {
            const statusText = {
                'success': '✓ 发送成功',
                'simulated': '○ 模拟发送',
                'no_email': '△ 无邮箱',
                'error': '✗ 发送失败'
            }[r.status] || r.status;
            return `${r.store_name}: ${statusText}${r.message ? ' - ' + r.message : ''}`;
        }).join('\n');
        alert(`邮件发送状态 (${data.success_count || 0}/${data.total || 0}):\n\n${detail}`);
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
