"""PDF and PNG figures for SIAN analysis exports."""
from collections import Counter
from io import BytesIO
import csv
import io
import math
import zipfile

import networkx as nx
from matplotlib.figure import Figure
from matplotlib.patches import Wedge, Circle


def lexical_chains(monograms, bigrams, trigrams, limit=12):
    bigram_counts = {row["ngram"]: int(row["count"]) for row in bigrams}
    chains, used = [], set()
    for row in monograms:
        term = row["term"]
        for triple in trigrams:
            trigram = triple["ngram"]
            tokens = trigram.split()
            if trigram in used or len(tokens) != 3:
                continue
            candidates = [" ".join(pair) for pair in (tokens[:2], tokens[1:])
                          if term in pair and " ".join(pair) in bigram_counts]
            if candidates:
                bigram = max(candidates, key=bigram_counts.get)
                chains.append((term, int(row["count"]), bigram, bigram_counts[bigram],
                               trigram, int(triple["count"])))
                used.add(trigram)
                break
        if len(chains) == limit:
            break
    return chains


def flower_figure(chains, maxima, document_count):
    bg, ink, soft = '#f8f7f3', '#172f37', '#476168'
    cols = ['#237c79', '#4c65a2', '#b4583c']
    fig=Figure(figsize=(14,8),facecolor=bg)
    fig.text(.055,.931,'SIAN  /  ANÁLISIS DEL CORPUS',fontsize=12,color=cols[0],weight='bold')
    fig.text(.055,.865,'Flor de relaciones léxicas',fontsize=34,color=ink,weight='bold')
    fig.text(.055,.817,f'Monograma → bigrama → trigrama  |  {document_count:,} documentos analizados',fontsize=13,color=soft)
    ax = fig.add_axes([.04,.15,.45,.61], aspect='equal')
    ax.set(xlim=(-4,4), ylim=(-3.7,3.7))
    ax.axis('off')
    for r in (1,2,3): ax.add_patch(Circle((0,0),r,fill=False,ec='#d5ddda',lw=.9))
    sector = 360 / (len(chains) + 1)
    for i,(a,x,c,y,e,z) in enumerate(chains):
        theta=90-i*sector
        rad=math.radians(theta)
        for j,v in enumerate((x,y,z)):
            half=.43*sector*v/maxima[j]
            ax.add_patch(Wedge((0,0),j+1,theta-half,theta+half,width=.93,fc=cols[j],ec='none'))
        ax.text(3.43*math.cos(rad),3.43*math.sin(rad),a,ha='center',va='center',fontsize=9,color=ink,weight='bold')
    for i,(c,label) in enumerate(zip(cols,['1 · Monograma','2 · Bigrama','3 · Trigrama'])):
        fig.text(.07+i*.13,.126,'●',color=c,fontsize=11)
        fig.text(.085+i*.13,.126,label,color=ink,fontsize=10)
    ax2 = fig.add_axes([.50,.145,.46,.60])
    ax2.axis('off')
    ax2.text(0,1.02,'Cadenas y frecuencias',fontsize=17,color=ink,weight='bold',transform=ax2.transAxes)
    for i,(a,x,c,y,e,z) in enumerate(chains):
        yy= .94-i*.072
        if i%2==0: ax2.axhspan(yy-.027,yy+.036,color='#ecefec',zorder=0)
        ax2.text(.012,yy,a,va='center',color=cols[0],fontsize=10,weight='bold')
        ax2.text(.19,yy,c,va='center',color=cols[1],fontsize=10)
        ax2.text(.46,yy,e,va='center',color=cols[2],fontsize=10)
        ax2.text(.99,yy,f'{x:,} / {y:,} / {z:,}'.replace(',',' '),ha='right',va='center',color=ink,fontsize=9)
    ax2.set(xlim=(0,1),ylim=(0,1))
    fig.text(.055,.063,'Cada anillo usa el máximo de su propio orden. El ancho angular representa frecuencia relativa; la tabla muestra los conteos.',fontsize=10,color=soft)
    fig.text(.055,.036,'Los enlaces indican inclusión de palabras consecutivas en los n-gramas exportados. Algunas cadenas corresponden a referencias bibliográficas.',fontsize=10,color=soft)
    return fig

def _render(figure, format):
    buffer = BytesIO()
    figure.savefig(buffer, format=format, dpi=180)
    return buffer.getvalue()


def lexical_figure_files(monograms, bigrams, trigrams, document_count):
    datasets = [monograms, bigrams, trigrams]
    maxima = [max((int(row["count"]) for row in rows), default=1) or 1 for rows in datasets]
    chains = lexical_chains(*datasets)
    files = {}
    if chains:
        figure = flower_figure(chains, maxima, document_count)
        files["figuras/flor_lexica.pdf"] = _render(figure, "pdf")
        files["figuras/flor_lexica.png"] = _render(figure, "png")
    table = io.StringIO(newline="")
    writer = csv.writer(table)
    writer.writerow(["monograma", "frecuencia_1", "bigrama", "frecuencia_2", "trigrama", "frecuencia_3"])
    writer.writerows(chains)
    files["datos/relaciones_flor.csv"] = table.getvalue().encode("utf-8")
    for name, key, rows in zip(("monogramas", "bigramas", "trigramas"), ("term", "ngram", "ngram"), datasets):
        if not rows:
            continue
        figure = Figure(figsize=(10, 7), layout="constrained")
        ax = figure.subplots()
        top = rows[:15][::-1]
        ax.barh([row[key] for row in top], [int(row["count"]) for row in top], color="#237c79")
        ax.set(title=f"SIAN · {name.capitalize()} más frecuentes", xlabel="Frecuencia en el corpus analizado")
        for extension in ("pdf", "png"):
            files[f"figuras/{name}.{extension}"] = _render(figure, extension)
    return files


def network_figure_files(networks):
    """Render a readable strongest-edge view of each exported network."""
    files = {}
    for name, title, network in networks:
        nodes = {node["id"]: node for node in network["nodes"]}
        edges = sorted(
            network["edges"],
            key=lambda edge: float(edge.get("raw_weight") or edge["weight"]),
            reverse=True,
        )[:20]
        graph = nx.MultiDiGraph()
        for edge in edges:
            graph.add_edge(edge["source"], edge["target"],
                           weight=float(edge.get("raw_weight") or edge["weight"]))
        figure = Figure(figsize=(13, 9))
        ax = figure.subplots()
        ax.set_axis_off()
        figure.suptitle(f"SIAN · {title}", fontsize=22)
        if edges:
            positions = nx.spring_layout(graph.to_undirected(), seed=42)
            weights = [weight for _, _, weight in graph.edges(data="weight")]
            maximum = max(weights) or 1
            nx.draw_networkx_edges(graph, positions, ax=ax, alpha=.45, arrows=False,
                                   width=[.7 + 3 * weight / maximum for weight in weights])
            nx.draw_networkx_nodes(graph, positions, ax=ax, node_color="#237c79", node_size=180)
            labels = {node: nodes.get(node, {}).get("label") or str(node) for node in graph}
            for node, (x, y) in positions.items():
                ax.annotate(labels[node], (x, y), xytext=(0, 8), textcoords="offset points",
                            ha="center", fontsize=8, bbox={"fc": "white", "ec": "none", "alpha": .85})
            ax.margins(.2)
            figure.text(.5, .045, f"{len(edges)} aristas de mayor peso · {len(graph)} nodos", ha="center")
        else:
            ax.text(.5, .5, "Sin aristas en el análisis seleccionado", ha="center", va="center")
        for extension in ("pdf", "png"):
            files[f"figuras/redes/{name}.{extension}"] = _render(figure, extension)
    return files


def narrative_figure_files(narrative_graph, timeline, event_summary):
    actors = {
        "nodes": [node for node in narrative_graph["nodes"] if node["node_type"] == "actor"],
        "edges": [edge for edge in narrative_graph["edges"] if edge["edge_type"] == "actor_co_document"],
    }
    files = network_figure_files([
        ("actores", "Entidades extraídas que aparecen en el mismo documento", actors),
    ])

    stages = Figure(figsize=(9, 4.5), layout="constrained")
    ax = stages.subplots()
    ax.barh([row["narrative_stage"] for row in event_summary],
            [row["documents_with_stage"] for row in event_summary], color="#237c79")
    ax.invert_yaxis()
    ax.set(title="SIAN · Etapas narrativas detectadas", xlabel="Documentos con la etapa")
    if not event_summary:
        ax.text(.5, .5, "Sin etapas detectadas", ha="center", transform=ax.transAxes)

    documents_by_year = Counter()
    for row in timeline:
        documents_by_year[int(row["year"])] += row["documents"]
    years = sorted(documents_by_year)
    chronology = Figure(figsize=(10, 4.5), layout="constrained")
    ax = chronology.subplots()
    ax.bar(years, [documents_by_year[year] for year in years], color="#237c79")
    ax.set(title=f"SIAN · Cronología de registros fechados ({sum(documents_by_year.values()):,})",
           xlabel="Año", ylabel="Documentos")
    if not years:
        ax.text(.5, .5, "Sin fechas disponibles", ha="center", transform=ax.transAxes)

    for name, figure in (("etapas_narrativas", stages), ("cronologia", chronology)):
        for extension in ("pdf", "png"):
            files[f"figuras/{name}.{extension}"] = _render(figure, extension)
    return files


def analysis_zip(files):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=4) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()
