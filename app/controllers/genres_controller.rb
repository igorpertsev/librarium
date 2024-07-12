class GenresController < ApplicationController
  def index
    @genres = Genre.all
  end

  def new
    @genre = Genre.new
  end

  def create
    @genre = Genre.new(genre_params)
    if @genre.save
      respond_to do |format|
        format.html { redirect_to genres_path }
        format.turbo_stream
      end
    else
      render :new
    end
  end

  def edit
    @genre = Genre.find(params[:id])
  end

  def update
    @genre = Genre.find(params[:id])
    if @genre.update(genre_params)
      respond_to do |format|
        format.html { redirect_to @genre }
        format.turbo_stream
      end
    else
      render :edit
    end
  end

  def destroy
    @genre = Genre.find(params[:id])
    @genre.destroy
    respond_to do |format|
      format.html { redirect_to genres_path }
      format.turbo_stream
    end
  end

  private

  def genre_params
    params.require(:genre).permit(:name)
  end
end
