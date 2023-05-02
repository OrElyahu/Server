import argparse
import os
import uuid

import firebase_admin

import DBUtils
import objects.Utils
from objects.Path import A11y
from objects.Utils import JsonEncoder
from flask import Flask, jsonify, request
from flask_restful import Api, reqparse, abort
from firebase_admin import credentials, firestore, storage

app = Flask(__name__)
app.json_encoder = JsonEncoder
api = Api(app)
cred = credentials.Certificate('admin-key.json')
firebase_admin.initialize_app(cred)
db = firestore.client()
bucket = storage.bucket('navigate-a1e16.appspot.com')

sites = {doc.id: DBUtils.des_site(doc) for doc in db.collection(u'sites').stream()}


@app.route('/upload_report', methods=['POST'])
def upload_report():
    parser = reqparse.RequestParser()
    report_id = str(uuid.uuid4())
    parser.add_argument('reporter_email', type=str, required=True)
    parser.add_argument('description', type=str, required=True)
    parser.add_argument('wp_id', type=str, required=True)
    parser.add_argument('direction', type=int, required=True)
    parser.add_argument('site_name', type=str, required=True)
    image_file = request.files['image']
    extension = os.path.splitext(image_file.filename)[1]
    if extension not in ['jpg', 'jpeg']:
        abort(400, message=f"File with extension : {extension} is invalid. Must be jpeg/jpg.")

    args = parser.parse_args()

    # save image to Storage under reports section
    blob = bucket.blob('reports/' + report_id)
    blob.upload_from_file(image_file, content_type='image/jpeg')
    url = blob.public_url

    report_ref = db.collection('reports')

    report_data = {
        'reporter_email': args['reporter_email'],
        'description': args['description'],
        'wp_id': args['wp_id'],
        'direction': args['direction'],
        'site_name': args['site_name']
    }

    # add the document to the collection with the report_id as the document ID
    report_ref.document(report_id).set(report_data)

    return {'success': 'Report added successfully'}, 200


@app.route('/get_site', methods=['GET'])
def get_site():
    parser = reqparse.RequestParser()
    parser.add_argument('site_name', type=str, required=True)
    args = parser.parse_args()
    site_name = args['site_name']
    if site_name not in sites:
        abort(404, message=f"Site : {site_name} not found")

    return jsonify(sites[site_name])


@app.route('/shortest_path', methods=['GET'])
def shortest_path():
    parser = reqparse.RequestParser()
    parser.add_argument('site_name', type=str, required=True)
    parser.add_argument('poi_start', type=str, required=True)
    parser.add_argument('poi_end', type=str, required=True)
    parser.add_argument('a11y', type=str, default=A11y.WALK.name)
    args = {}
    try:
        args = parser.parse_args()
    except argparse.ArgumentError as e:
        abort(400, message=f"Params not given properly.")

    site_name = args['site_name']
    poi_start = args['poi_start']
    poi_end = args['poi_end']

    if args['a11y'] not in A11y.__members__:
        abort(400, message=f"param {args['a11y']} is not given properly")
    a11y = A11y[args['a11y']]

    if site_name not in sites:
        abort(404, message=f"Site : {site_name} not found")

    site = sites[site_name]
    graphs = site.get_graphs()
    start_graph = next((graph for graph in graphs if poi_start in graph.get_poi_wps()), None)
    end_graph = next((graph for graph in graphs if poi_end in graph.get_poi_wps()), None)
    if not start_graph:
        abort(404, message=f"Point of interest: {poi_start} not found in {site_name}")
    if not end_graph:
        abort(404, message=f"Point of interest: {poi_end} not found in {site_name}")
    if start_graph is not end_graph:
        # TODO: handle multiple graphs
        abort(501, message=f"Point of interests found in separate locations in {site_name}, "
                           "navigation between them not implemented yet.")
    graph = start_graph
    start_id = graph.get_poi_wps()[poi_start]
    end_id = graph.get_poi_wps()[poi_end]
    short_path = graph.shortest_path(start_id, end_id, a11y)
    if not short_path:
        abort(404, message=f"Unable to find path from {poi_start} to {poi_end}")
    return jsonify(short_path)


if __name__ == "__main__":
    app.run(debug=True)
