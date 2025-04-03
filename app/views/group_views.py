from flask import Blueprint, render_template, request, redirect, url_for
from db_interface import get_all_groups, add_group, update_group_description, delete_group

group = Blueprint('group', __name__, url_prefix='/group')


@group.route('/')
def group_list():
    available_groups = get_all_groups()
    return render_template('group_list.html', available_groups=available_groups)


@group.route('/add', methods=['POST'])
def add_group_route():
    vlan_id = request.form['vlan_id']
    desc = request.form.get('description', '')
    add_group(vlan_id, desc)
    return redirect(url_for('group.group_list'))


@group.route('/update_description', methods=['POST'])
def update_description_route():
    group_id = request.form['group_id']
    desc = request.form.get('description', '')
    update_group_description(group_id, desc)
    return redirect(url_for('group.group_list'))


@group.route('/delete', methods=['POST'])
def delete_group_route():
    group_id = request.form['group_id']
    delete_group(group_id)
    return redirect(url_for('group.group_list'))
