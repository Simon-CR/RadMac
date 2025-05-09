from flask import Blueprint, render_template, request, redirect, url_for, flash
from db_interface import (
    get_all_users,
    get_all_groups,
    add_user,
    update_user,
    delete_user,
    refresh_vendors,
    get_user_by_mac
)

user = Blueprint('user', __name__, url_prefix='/user')


@user.route('/')
def user_list():
    users = get_all_users()
    available_groups = get_all_groups()
    return render_template('user_list.html', users=users, available_groups=available_groups)


@user.route('/add', methods=['POST'])
def add():
    mac = request.form['mac_address']
    desc = request.form.get('description', '')
    group_id = request.form['group_id']
    add_user(mac, desc, group_id)
    return redirect(url_for('user.user_list'))

@user.route('/update_user', methods=['POST'])
def update_user_route():
    mac = request.form['mac_address']
    desc = request.form.get('description', '')
    vlan_id = request.form['group_id']
    update_user(mac, desc, vlan_id)
    return redirect(url_for('user.user_list'))

@user.route('/delete', methods=['POST'])
def delete():
    mac = request.form['mac_address']
    delete_user(mac)
    return redirect(url_for('user.user_list'))


@user.route('/refresh_vendors', methods=['POST'])
def refresh():
    refresh_vendors()
    return {'status': 'OK'}
