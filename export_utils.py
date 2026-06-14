import os
from datetime import datetime, timedelta
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from extensions import db
from models import Store, Employee, Schedule

def export_to_excel(start_date_str, end_date_str):
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    
    stores = Store.query.all()
    
    wb = Workbook()
    wb.remove(wb.active)
    
    header_font = Font(bold=True, size=12, color='FFFFFF')
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    subheader_fill = PatternFill(start_color='8EA9DB', end_color='8EA9DB', fill_type='solid')
    center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    summary_ws = wb.create_sheet('排班汇总')
    
    summary_ws.merge_cells('A1:H1')
    summary_ws['A1'] = f'员工排班汇总表 ({start_date_str} 至 {end_date_str})'
    summary_ws['A1'].font = Font(bold=True, size=16)
    summary_ws['A1'].alignment = center_align
    summary_ws.row_dimensions[1].height = 30
    
    headers = ['门店', '日期', '时段', '人员名单', '人数', '高级员工数', '是否满足最低人数', '备注']
    for col, header in enumerate(headers, 1):
        cell = summary_ws.cell(row=3, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border
    
    row = 4
    current_date = start_date
    while current_date <= end_date:
        day_name = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][current_date.weekday()]
        
        for store in stores:
            schedules = Schedule.query.filter_by(
                store_id=store.id,
                date=current_date
            ).all()
            
            time_slots = _get_time_slots(store, schedules)
            
            for slot in time_slots:
                staff_names = '、'.join([s['name'] for s in slot['staff']]) if slot['staff'] else '-'
                senior_count = slot['senior_count']
                meets_min = '是' if slot['meets_minimum'] else '否'
                remark = '' if slot['meets_minimum'] else '人手不足'
                
                summary_ws.cell(row=row, column=1, value=store.name).border = thin_border
                summary_ws.cell(row=row, column=2, value=f'{current_date.isoformat()} {day_name}').border = thin_border
                summary_ws.cell(row=row, column=3, value=slot['time']).border = thin_border
                summary_ws.cell(row=row, column=4, value=staff_names).border = thin_border
                summary_ws.cell(row=row, column=5, value=slot['count']).border = thin_border
                summary_ws.cell(row=row, column=6, value=senior_count).border = thin_border
                
                meets_cell = summary_ws.cell(row=row, column=7, value=meets_min)
                meets_cell.border = thin_border
                if not slot['meets_minimum']:
                    meets_cell.fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')
                
                summary_ws.cell(row=row, column=8, value=remark).border = thin_border
                
                for col in range(1, 9):
                    summary_ws.cell(row=row, column=col).alignment = center_align
                
                row += 1
        
        current_date += timedelta(days=1)
    
    for col in range(1, 9):
        summary_ws.column_dimensions[get_column_letter(col)].width = [12, 18, 10, 40, 8, 12, 14, 15][col-1]
    
    for store in stores:
        ws = wb.create_sheet(f'{store.name}排班')
        
        ws.merge_cells('A1:I1')
        ws['A1'] = f'{store.name} 排班详情 ({start_date_str} 至 {end_date_str})'
        ws['A1'].font = Font(bold=True, size=14)
        ws['A1'].alignment = center_align
        ws.row_dimensions[1].height = 25
        
        ws['A2'] = f'营业时间：{store.open_time} - {store.close_time}'
        ws['A2'].font = Font(italic=True)
        ws.merge_cells('A2:I2')
        
        day_headers = ['日期/员工']
        current = start_date
        while current <= end_date:
            day_name = ['一', '二', '三', '四', '五', '六', '日'][current.weekday()]
            day_headers.append(f'{current.month}/{current.day}\n周{day_name}')
            current += timedelta(days=1)
        
        for col, header in enumerate(day_headers, 1):
            cell = ws.cell(row=4, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = thin_border
        
        employees = Employee.query.all()
        for row_idx, emp in enumerate(employees, 5):
            ws.cell(row=row_idx, column=1, value=f'{emp.name}({emp.skill_level})').border = thin_border
            ws.cell(row=row_idx, column=1).alignment = center_align
            
            current = start_date
            for col_idx in range(2, len(day_headers) + 1):
                sched = Schedule.query.filter_by(
                    employee_id=emp.id,
                    store_id=store.id,
                    date=current
                ).first()
                
                if sched:
                    value = f'{sched.start_time}-{sched.end_time}'
                    cell = ws.cell(row=row_idx, column=col_idx, value=value)
                    if emp.skill_level == '高级':
                        cell.fill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
                else:
                    value = ''
                    cell = ws.cell(row=row_idx, column=col_idx, value=value)
                
                cell.border = thin_border
                cell.alignment = center_align
                current += timedelta(days=1)
        
        ws.column_dimensions['A'].width = 16
        for col in range(2, len(day_headers) + 1):
            ws.column_dimensions[get_column_letter(col)].width = 12
    
    workhours_ws = wb.create_sheet('工时统计')
    
    workhours_ws.merge_cells('A1:F1')
    workhours_ws['A1'] = f'员工工时统计 ({start_date_str} 至 {end_date_str})'
    workhours_ws['A1'].font = Font(bold=True, size=14)
    workhours_ws['A1'].alignment = center_align
    workhours_ws.row_dimensions[1].height = 25
    
    headers = ['员工姓名', '技能等级', '排班天数', '总工时(小时)', '标准工时', '是否超时']
    for col, header in enumerate(headers, 1):
        cell = workhours_ws.cell(row=3, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border
    
    employees = Employee.query.all()
    for row_idx, emp in enumerate(employees, 4):
        schedules = Schedule.query.filter(
            Schedule.employee_id == emp.id,
            Schedule.date >= start_date,
            Schedule.date <= end_date
        ).all()
        
        total_hours = sum(s._get_duration() for s in schedules)
        total_hours = round(total_hours, 1)
        standard_hours = 160
        is_overtime = total_hours > standard_hours
        
        workhours_ws.cell(row=row_idx, column=1, value=emp.name).border = thin_border
        workhours_ws.cell(row=row_idx, column=2, value=emp.skill_level).border = thin_border
        workhours_ws.cell(row=row_idx, column=3, value=len(set(s.date for s in schedules))).border = thin_border
        workhours_ws.cell(row=row_idx, column=4, value=total_hours).border = thin_border
        workhours_ws.cell(row=row_idx, column=5, value=standard_hours).border = thin_border
        
        overtime_cell = workhours_ws.cell(row=row_idx, column=6, value='是' if is_overtime else '否')
        overtime_cell.border = thin_border
        if is_overtime:
            overtime_cell.fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')
        
        for col in range(1, 7):
            workhours_ws.cell(row=row_idx, column=col).alignment = center_align
    
    for col in range(1, 7):
        workhours_ws.column_dimensions[get_column_letter(col)].width = [15, 12, 12, 15, 12, 12][col-1]
    
    file_path = os.path.join(os.path.dirname(__file__), 'temp_schedule.xlsx')
    wb.save(file_path)
    return file_path

def _get_time_slots(store, schedules):
    from datetime import datetime, timedelta
    
    open_time = datetime.strptime(store.open_time, '%H:%M')
    close_time = datetime.strptime(store.close_time, '%H:%M')
    
    slots = []
    current = open_time
    while current < close_time:
        next_hour = current + timedelta(hours=1)
        slot_str = current.strftime('%H:%M')
        
        staff_in_slot = []
        for sched in schedules:
            sched_start = datetime.strptime(sched.start_time, '%H:%M')
            sched_end = datetime.strptime(sched.end_time, '%H:%M')
            if sched_start <= current and sched_end > current:
                staff_in_slot.append({
                    'name': sched.employee.name,
                    'skill_level': sched.employee.skill_level
                })
        
        slots.append({
            'time': slot_str,
            'staff': staff_in_slot,
            'count': len(staff_in_slot),
            'senior_count': len([s for s in staff_in_slot if s['skill_level'] == '高级']),
            'meets_minimum': len(staff_in_slot) >= store.min_staff
        })
        
        current = next_hour
    
    return slots
