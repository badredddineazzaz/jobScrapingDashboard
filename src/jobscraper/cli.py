"""Interface en ligne de commande pour JobScraper."""

import json
from pathlib import Path
from typing import List, Optional

import click
from loguru import logger
from rich.console import Console
from rich.table import Table

from jobscraper.models.job import (
    ContractType,
    DatePosted,
    ExperienceLevel,
    SearchCriteria,
    SortBy,
    WorkplaceType,
)
from jobscraper.services.search import SearchEvent, SearchEventType, SearchService

console = Console()


def setup_logging(verbose: bool) -> None:
    """Configure le logging."""
    import sys

    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=level)


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Mode verbose")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """JobScraper - Outil de scraping d'offres d'emploi."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)


@main.command()
@click.option("--keywords", "-k", multiple=True, help="Mots-clés de recherche")
@click.option("--title", "-t", help="Titre de poste exact (recherche précise)")
@click.option("--location", "-l", default="France", help="Localisation (ville, région, pays)")
@click.option("--radius", "-r", type=click.Choice(["5", "10", "25", "50", "100"]), help="Rayon de recherche en km")
@click.option("--contract", "-c", multiple=True,
              type=click.Choice(["cdi", "cdd", "stage", "alternance", "interim", "freelance"]),
              help="Type de contrat")
@click.option("--experience", "-e", multiple=True,
              type=click.Choice(["internship", "junior", "mid", "senior", "lead", "director"]),
              help="Niveau d'expérience")
@click.option("--workplace", "-w", multiple=True,
              type=click.Choice(["on_site", "remote", "hybrid"]),
              help="Type de lieu de travail")
@click.option("--date", type=click.Choice(["past_24h", "past_week", "past_month", "any_time"]),
              default="any_time", help="Date de publication")
@click.option("--sort", type=click.Choice(["relevance", "date"]), default="relevance",
              help="Tri des résultats")
@click.option("--company", multiple=True, help="Entreprises spécifiques")
@click.option("--max-results", "-n", default=50, help="Nombre maximum de résultats")
@click.option("--output", "-o", type=click.Path(), help="Fichier de sortie")
@click.option("--format", "output_format", type=click.Choice(["json", "csv", "table"]), default="table")
@click.option("--details", "-d", is_flag=True, help="Récupérer les détails complets")
@click.option("--source", "-s", multiple=True,
              type=click.Choice(["linkedin", "hellowork", "francetravail", "adzuna", "wttj", "all"]),
              default=["linkedin", "hellowork", "francetravail", "adzuna", "wttj"], help="Sources: linkedin, hellowork, francetravail, adzuna (Indeed+Monster), wttj, all")
@click.pass_context
def search(
    ctx: click.Context,
    keywords: tuple,
    title: Optional[str],
    location: str,
    radius: Optional[str],
    contract: tuple,
    experience: tuple,
    workplace: tuple,
    date: str,
    sort: str,
    company: tuple,
    max_results: int,
    output: Optional[str],
    output_format: str,
    details: bool,
    source: tuple,
) -> None:
    """
    Recherche des offres d'emploi sur plusieurs sources.

    Exemples:

      # Recherche LinkedIn (défaut)
      jobscraper search -k python -l Paris

      # Recherche WTTJ uniquement
      jobscraper search -k python -l Paris -s wttj

      # Recherche sur toutes les sources
      jobscraper search -k python -l Paris -s all

      # Recherche CDI senior en remote
      jobscraper search -k "data engineer" -c cdi -e senior -w remote

      # Export JSON avec détails
      jobscraper search -k python -n 100 --details -o jobs.json
    """
    # Construire les critères de recherche
    criteria = SearchCriteria(
        keywords=list(keywords) if keywords else [],
        title=title,
        location=location,
        radius_km=int(radius) if radius else None,
        contract_types=[ContractType(c) for c in contract] if contract else [],
        experience_levels=[ExperienceLevel(e) for e in experience] if experience else [],
        workplace_types=[WorkplaceType(w) for w in workplace] if workplace else [],
        date_posted=DatePosted(date) if date else None,
        sort_by=SortBy(sort),
        companies=list(company) if company else [],
        max_results=max_results,
    )

    # Affichage des critères
    console.print(f"[bold blue]Recherche d'offres d'emploi...[/bold blue]")
    if criteria.title:
        console.print(f"Titre: \"{criteria.title}\"")
    if criteria.keywords:
        console.print(f"Mots-clés: {', '.join(criteria.keywords)}")
    console.print(f"Localisation: {criteria.location}")
    if criteria.radius_km:
        console.print(f"Rayon: {criteria.radius_km} km")
    if criteria.contract_types:
        console.print(f"Contrat: {', '.join(c.value for c in criteria.contract_types)}")
    if criteria.experience_levels:
        console.print(f"Expérience: {', '.join(e.value for e in criteria.experience_levels)}")
    if criteria.workplace_types:
        console.print(f"Lieu: {', '.join(w.value for w in criteria.workplace_types)}")
    if criteria.date_posted and criteria.date_posted != DatePosted.ANY_TIME:
        console.print(f"Date: {criteria.date_posted.value}")
    if criteria.sort_by == SortBy.DATE:
        console.print("Tri: Plus récent")
    if details:
        console.print("[dim]Mode détaillé activé[/dim]")

    search_service = SearchService()
    sources_to_use = list(source)
    if "all" in sources_to_use:
        sources_to_use = search_service.available_sources()
    console.print(f"Sources: {', '.join(sources_to_use)}")

    def render_progress(event: SearchEvent) -> None:
        """Render service events without coupling orchestration to Rich."""

        if event.type == SearchEventType.SOURCE_STARTED:
            console.print(f"[dim]Démarrage {event.source}...[/dim]")
        elif event.type == SearchEventType.SOURCE_COMPLETED:
            console.print(
                f"[green]{event.source}: {event.source_job_count} offres[/green]"
            )
        elif event.type == SearchEventType.SOURCE_FAILED:
            console.print(f"[red]{event.source}: {event.error}[/red]")

    result = search_service.search(
        criteria,
        sources=sources_to_use,
        include_details=details,
        on_event=render_progress,
    )
    jobs = result.jobs

    if not jobs:
        console.print("[yellow]Aucune offre trouvée.[/yellow]")
        return

    console.print(f"\n[bold green]{len(jobs)} offres trouvées![/bold green]\n")

    # Affichage selon le format demandé
    if output_format == "table" and not output:
        display_jobs_table(jobs)
    elif output_format == "json" or (output and output.endswith(".json")):
        save_jobs_json(jobs, output)
    elif output_format == "csv" or (output and output.endswith(".csv")):
        save_jobs_csv(jobs, output)
    else:
        display_jobs_table(jobs)


def display_jobs_table(jobs: List) -> None:
    """Affiche les offres dans un tableau."""
    table = Table(title="Offres d'emploi")
    table.add_column("Titre", style="cyan", no_wrap=True)
    table.add_column("Entreprise", style="magenta")
    table.add_column("Localisation", style="green")
    table.add_column("Source")

    for job in jobs[:20]:  # Limiter l'affichage
        table.add_row(
            job.title[:40] + "..." if len(job.title) > 40 else job.title,
            job.company[:25] + "..." if len(job.company) > 25 else job.company,
            job.location[:20] + "..." if len(job.location) > 20 else job.location,
            job.source,
        )

    console.print(table)

    if len(jobs) > 20:
        console.print(f"\n[dim]... et {len(jobs) - 20} autres offres[/dim]")


def save_jobs_json(jobs: List, output: Optional[str]) -> None:
    """Sauvegarde les offres en JSON."""
    data = [job.model_dump(mode="json") for job in jobs]

    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        console.print(f"[green]Offres sauvegardées dans {output}[/green]")
    else:
        console.print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def save_jobs_csv(jobs: List, output: Optional[str]) -> None:
    """Sauvegarde les offres en CSV."""
    import csv
    from io import StringIO

    fieldnames = [
        "id", "source", "title", "company", "location", "url",
        "contract_type", "experience_level", "remote", "posted_at", "description"
    ]

    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for job in jobs:
                writer.writerow({k: getattr(job, k, "") for k in fieldnames})
        console.print(f"[green]Offres sauvegardées dans {output}[/green]")
    else:
        output_buffer = StringIO()
        writer = csv.DictWriter(output_buffer, fieldnames=fieldnames)
        writer.writeheader()
        for job in jobs:
            writer.writerow({k: str(getattr(job, k, "")) for k in fieldnames})
        console.print(output_buffer.getvalue())


@main.command()
def sources() -> None:
    """Liste les sources disponibles."""
    table = Table(title="Sources disponibles")
    table.add_column("Source", style="cyan")
    table.add_column("Statut", style="green")
    table.add_column("Description")

    sources_info = [
        ("LinkedIn", "Actif", "Offres d'emploi LinkedIn"),
        ("HelloWork", "Actif", "Offres d'emploi HelloWork"),
        ("France Travail", "Actif", "Ex Pôle Emploi"),
        ("Adzuna", "Actif*", "Agrégateur (Indeed, Monster) - nécessite clés API"),
        ("Welcome to the Jungle", "Actif", "Startups et scale-ups (via Algolia)"),
        ("Apec", "À venir", "Cadres et jeunes diplômés"),
    ]

    for source, status, description in sources_info:
        table.add_row(source, status, description)

    console.print(table)


if __name__ == "__main__":
    main()
