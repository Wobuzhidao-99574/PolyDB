# =====================================================
# 文件名：routes/main.py
# 作用：处理所有页面的路由逻辑
# =====================================================

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, make_response, jsonify, Response
)
from config import Config

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    return redirect(url_for('main.home'))


@main_bp.route('/home')
def home():
    return render_template('index.html')


@main_bp.route('/history')
def history():
    return render_template('history.html')


ALL_COLUMNS = [
    'id', 'formula', 'mw', 'tpsa', 'logp', 'energy',
    'hba', 'hbd', 'rotb', 'sa', 'qed', 'pains', 'chembl_id',
    'smiles', 'name', 'category'
]
NUM_COLUMNS = {'mw', 'tpsa', 'logp', 'energy', 'hba', 'hbd', 'rotb', 'sa', 'qed'}


@main_bp.route('/search/advanced', methods=['GET', 'POST'])
def search_advanced():
    result_df = None
    total_records = 0
    total_pages = 1
    error_msg = None

    page = int(request.args.get('page', 1))
    category = request.args.get('category', 'ALL')
    extra_cond = request.args.get('extra_cond', '')
    sort_by  = request.args.get('sort_by', '')
    sort_dir = request.args.get('sort_dir', 'asc')
    selected_cols = request.args.getlist('cols') or ALL_COLUMNS

    if request.method == 'POST':
        category = request.form.get('category', 'ALL')
        selected_cols = [c for c in ALL_COLUMNS if request.form.get(f'col_{c}')] or ALL_COLUMNS
        extra_cond = request.form.get('extra_cond', '').strip()
        sort_by  = request.form.get('sort_by', '')
        sort_dir = request.form.get('sort_dir', 'asc')
        params = {'page': 1, 'category': category, 'extra_cond': extra_cond, 'sort_by': sort_by, 'sort_dir': sort_dir}
        base_url = url_for('main.search_advanced', **params)
        cols_qs = '&'.join(f'cols={c}' for c in selected_cols)
        return redirect(f"{base_url}&{cols_qs}")

    try:
        from services.polydb_service import advanced_search
        result_df, total_records = advanced_search(
            category=category,
            extra_conditions=extra_cond,
            selected_columns=selected_cols,
            page=page,
            page_size=Config.PAGE_SIZE,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        total_pages = max(1, (total_records + Config.PAGE_SIZE - 1) // Config.PAGE_SIZE)
    except Exception as e:
        error_msg = str(e)

    img_dict = {}
    if result_df is not None and not result_df.empty and 'smiles' in result_df.columns and len(result_df) <= 20:
        from services.chemistry_service import smiles_to_base64
        for smi in result_df['smiles'].tolist():
            if smi and smi not in img_dict:
                img_dict[smi] = smiles_to_base64(smi)

    return render_template(
        'search_advanced.html',
        all_columns=ALL_COLUMNS,
        num_columns=NUM_COLUMNS,
        selected_cols=selected_cols,
        category=category,
        extra_cond=extra_cond,
        result_df=result_df,
        total_records=total_records,
        total_pages=total_pages,
        page=page,
        error_msg=error_msg,
        img_dict=img_dict,
        page_size=Config.PAGE_SIZE,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@main_bp.route('/search/similarity', methods=['GET', 'POST'])
def search_similarity():
    result_rows = []
    error_msg = None
    smiles_in = ''
    sim_min = 0.0
    sim_max = 1.0

    if request.method == 'POST':
        smiles_in = request.form.get('smiles', '').strip()
        try:
            sim_min = float(request.form.get('sim_min', 0.0))
            sim_max = float(request.form.get('sim_max', 1.0))
        except ValueError:
            sim_min, sim_max = 0.0, 1.0

        if smiles_in:
            try:
                from rdkit import Chem
                from rdkit.Chem import AllChem
                from services.polydb_service import search_similar_molecules
                from services.chemistry_service import (
                    pil_to_base64, GasMaps, LogPMaps, Lipinski, smiles_to_base64
                )

                if Chem.MolFromSmiles(smiles_in) is None:
                    raise ValueError(f"无效的 SMILES: {smiles_in}")

                sim_df = search_similar_molecules(
                    smiles_in,
                    radius=Config.SIMILARITY_RADIUS,
                    top_n=Config.SIMILARITY_TOP_N,
                    sim_min=sim_min,
                    sim_max=sim_max,
                )

                for _, row in sim_df.iterrows():
                    d = row.to_dict()
                    smi = d.get('smiles', '')
                    mol = Chem.MolFromSmiles(smi)
                    if mol:
                        AllChem.Compute2DCoords(mol)
                        d['img']     = smiles_to_base64(smi)
                        d['gasmap']  = pil_to_base64(GasMaps(mol))
                        d['logpmap'] = pil_to_base64(LogPMaps(mol))
                    else:
                        d['img'] = d['gasmap'] = d['logpmap'] = ''
                    d['lipinski'] = Lipinski(
                        d.get('mw', 0), d.get('hba', 0), d.get('hbd', 0),
                        d.get('logp', 0), d.get('rotb', 0)
                    )
                    result_rows.append(d)

            except Exception as e:
                error_msg = str(e)

    return render_template(
        'search_similarity.html',
        smiles_in=smiles_in,
        sim_min=sim_min,
        sim_max=sim_max,
        result_rows=result_rows,
        error_msg=error_msg,
    )


@main_bp.route('/search/route', methods=['GET', 'POST'])
def search_route():
    main_result = None
    similar_results = None
    error_msg = None
    search_smile = ''
    sim_min = 0.0
    sim_max = 1.0
    reaction_conditions = {}
    names = {}

    try:
        from services.polydb_service import (
            find_by_smiles, find_similar_by_names,
            build_image_index, load_reaction_conditions
        )
        from services.chemistry_service import smiles_to_base64
        names = build_image_index()
        reaction_conditions = load_reaction_conditions()
    except Exception as e:
        error_msg = f"初始化失败: {e}"

    if request.method == 'POST' and not error_msg:
        search_smile = request.form.get('smiles', '').strip()
        sim_min = float(request.form.get('sim_min', 0.0))
        sim_max = float(request.form.get('sim_max', 1.0))

        if search_smile:
            try:
                from rdkit import Chem
                if Chem.MolFromSmiles(search_smile) is None:
                    raise ValueError(f"无效的 SMILES: {search_smile}")

                df1 = find_by_smiles(search_smile)
                if not df1.empty:
                    df1['img'] = df1['smiles'].apply(smiles_to_base64)
                    main_result = df1.to_dict('records')

                query_smi = df1['smiles'].iloc[0] if not df1.empty else search_smile
                df2 = find_similar_by_names(
                    list(names.keys()), query_smi,
                    sim_min=sim_min, sim_max=sim_max
                )
                if not df2.empty:
                    df2['img'] = df2['smiles'].apply(smiles_to_base64)
                    similar_results = df2.to_dict('records')

            except Exception as e:
                error_msg = str(e)

    return render_template(
        'search_route.html',
        search_smile=search_smile,
        sim_min=sim_min,
        sim_max=sim_max,
        main_result=main_result,
        similar_results=similar_results,
        names=names,
        reaction_conditions=reaction_conditions,
        error_msg=error_msg,
    )


@main_bp.route('/download')
def download():
    return render_template('download.html')


@main_bp.route('/download/csv')
def download_csv():
    try:
        from services.polydb_service import get_download_data
        csv_text = get_download_data()
        return Response(
            csv_text,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=polydb_id_smiles.csv'},
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@main_bp.route('/contact')
def contact():
    return render_template('contact.html')


@main_bp.route('/healthz')
def healthz():
    return jsonify({'ok': True}), 200